//! Owned by CNF-04. The normalizer: it turns an observation document into the form the
//! comparator compares, replacing exactly the values that
//! `specs/022-console-serving-parity/contracts/volatile-fields.json` lists and nothing
//! else.
//!
//! The rule is `contracts/parity-ledger.md` section 1.1: everything the server sends is
//! observable unless it is on the volatile list. The HTTP version token, the status line,
//! header names, header positions, header values other than `Date` and `Server`, JSON key
//! order, white space and escapes, stream framing, events, comments, files, log lines,
//! the engine tape and the exit status all stay as observed. The one derived value is the
//! `Content-Length` value (lead decision LD44): when it described the body received
//! exactly, it becomes the length of the normalized body. An over-lenient normalizer
//! would create parity that is not real, so:
//!
//! - every replacement names the list entry (or the rename-map entry) that allows it, in
//!   [`Normalized::applied`];
//! - a value is replaced only after its class check passes (an id of the listed length in
//!   lower-case hex, a time stamp inside the run window, a `Date` value in Python's
//!   IMF-fixdate form inside the run window, a non-negative figure, the server's own
//!   port, a path under the run's temporary directory); a value that fails the check
//!   stays as sent and is compared exactly;
//! - a number placeholder keeps the token's shape (`<num>` for digits, `<num:f>` with a
//!   fraction, `<num:e>` with an exponent), so an integer that turns into a float, or a
//!   float written in another notation, is still a difference;
//! - an id the client sent in a request body takes its number before the response of
//!   that exchange is read, so a server that replaces a client's id with a fresh one
//!   shows a difference;
//! - JSON is edited in place, token by token, and parsed again, so the text form and the
//!   parsed form of a body stay consistent and no formatting difference is hidden;
//! - a list entry the normalizer cannot apply (an unknown location, class or pattern hole)
//!   refuses to build the normalizer instead of being skipped.
//!
//! The rename map (`contracts/rename-map.json`) is applied to the reference side only,
//! and only its `decided` and `mechanical` entries, each in its own scope: `log` to log
//! lines, `file` to the last segment of an observed file path and to the value of a JSON
//! member named `file` or `to` that is a bare file name, `model-name` to the value of a
//! JSON member named `model` and to a `name` member of the same object that holds the
//! same value (the entries of `/api/tags` and `/api/ps`, project-maya
//! serve/model_api.py:69 and 78 at 7e68a30f), `text` to a whole JSON string, and `env` to an exact,
//! word-bounded variable name inside a JSON string or a log line. Other scopes name
//! browser-side or not yet settled text and rename nothing here.
//!
//! What is left out of the comparison document, because it is not something the server
//! sent or because it is fully determined by what is kept: the request bytes (the
//! client's own input; whether all of them were written is kept as `request_complete`),
//! the byte counts and SHA-256 digests beside each text (derived from the text), the wire
//! byte count of a disconnect (derived from the heads, the body and the client's read
//! sizes), the per-event raw bytes and field list of an event stream and the text of an
//! NDJSON line that parsed (all inside the body text, which is kept whole), and the
//! received wire bytes when they are exactly the heads followed by the body (written as
//! `"consistent"`; only after a `close` disconnect that fired and ended the read are bytes
//! past the recorded body, which arrived in the same read, client timing: after a
//! half-close the client reads on, so what the server sends after the body is kept).
//! Wire bytes that are not that concatenation (a chunked body, a malformed or headless
//! answer, bytes past a complete body) are kept, unnormalized.
//!
//! [`Normalizer::normalize`] takes an observation document as recorded, never one that
//! is already normalized: placeholder text in its input is reported as a problem. A
//! reference stored in its normalized form (the `document` of a [`Normalized`], a
//! committed golden) is replayed with [`Normalized::stored`], which refuses it unless it
//! is a fixed point of normalization (no raw volatile value left in it), and compared
//! with [`crate::compare::compare`]; it is never passed to the normalizer again.

mod classes;
mod json_text;
mod pattern;
mod stored;

use std::collections::BTreeMap;
use std::fmt;

use serde_json::{json, Map, Value};

use crate::observe::{sha256_hex, NdjsonParser, Observation, SseParser};
use crate::scenario::{Location, RenameMap, VolatileClass, VolatileFields};

pub use classes::RunWindow;
pub use json_text::MAX_DEPTH as MAX_JSON_DEPTH;
pub use pattern::MAX_PATTERN_TEXT;

use classes::Shape;
use json_text::Node;
use pattern::{Hole, Pattern, Piece};

/// The largest text the normalizer edits; a longer body, file or line is compared as
/// sent.
pub const MAX_TEXT_BYTES: usize = 64 * 1024 * 1024;

/// The most bytes a base64 text of the observation document may decode to: the client's
/// default limit on the bytes received (`client::ReadLimits::max_wire_bytes`), so that
/// any non-UTF-8 body or wire the client can record is compared as sent rather than
/// refused.
pub const MAX_DECODED_BYTES: usize = 72 * 1024 * 1024;

/// The most replacements recorded in [`Normalized::applied`]; replacements past it still
/// happen, and [`Normalized::applied_truncated`] is set.
pub const MAX_APPLIED: usize = 100_000;

/// The text every placeholder starts with, other than the substitution tokens.
pub const PLACEHOLDERS: &[&str] = &[
    "<epoch-s>",
    "<epoch-s:f>",
    "<iso>",
    "<num>",
    "<num:f>",
    "<num:e>",
    "<header>",
    "<pid>",
    "<rand>",
    "{{port}}",
    "{{tmp}}",
];

/// Which side of a comparison a document comes from.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Side {
    /// The reference: project-maya's observation. The rename map applies to it.
    Reference,
    /// The candidate: PulsarMLX Console's observation, compared as observed.
    Candidate,
}

/// What a side's class checks need to know about its run.
#[derive(Debug, Clone, PartialEq)]
pub struct SideContext {
    /// When the side ran.
    pub window: RunWindow,
    /// The port its server listened on, when known; without it no port is normalized.
    pub port: Option<u16>,
    /// Its temporary directories, as the server writes them (resolved, for example
    /// with `/private` on macOS); without one no path is normalized.
    pub tmp_dirs: Vec<String>,
    /// Seconds added to the end of the window for one field id, for a stamp that lies
    /// in the future by design (the `expires_at` of `/api/ps` is the idle limit after
    /// the last request). Fields not named here get none.
    pub window_extension: Vec<(String, f64)>,
}

impl SideContext {
    /// A context with a window and nothing else.
    pub fn new(window: RunWindow) -> Self {
        Self {
            window,
            port: None,
            tmp_dirs: Vec::new(),
            window_extension: Vec::new(),
        }
    }

    /// With the server's port.
    pub fn with_port(mut self, port: u16) -> Self {
        self.port = Some(port);
        self
    }

    /// With one more temporary directory.
    pub fn with_tmp_dir(mut self, dir: &str) -> Self {
        self.tmp_dirs.push(dir.to_string());
        self
    }

    /// With `seconds` added to the window end for the field `field_id`.
    pub fn extend_window(mut self, field_id: &str, seconds: f64) -> Self {
        self.window_extension.push((field_id.to_string(), seconds));
        self
    }

    fn extension(&self, field_id: &str) -> f64 {
        self.window_extension
            .iter()
            .filter(|(id, s)| id == field_id && s.is_finite() && *s > 0.0)
            .map(|(_, s)| *s)
            .fold(0.0, f64::max)
    }
}

/// A document the normalizer could not read, or a list it cannot apply.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NormalizeError {
    /// A JSON pointer to the value at fault (into the observation, or into the list).
    pub pointer: String,
    /// What is wrong.
    pub message: String,
}

impl fmt::Display for NormalizeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.pointer, self.message)
    }
}

impl std::error::Error for NormalizeError {}

fn err(pointer: &str, message: impl Into<String>) -> NormalizeError {
    NormalizeError {
        pointer: pointer.to_string(),
        message: message.into(),
    }
}

/// One replacement, and what allowed it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Applied {
    /// `volatile:<field id>` for a list entry, `rename:<deviation id>` for a rename-map
    /// entry.
    pub source: String,
    /// Where, as a JSON pointer into the comparison document (into the text that holds
    /// it, for a value inside a body, a line or a file).
    pub pointer: String,
}

/// Something in a side's document that makes its comparison unreliable; the comparator
/// reports each as a difference.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Issue {
    /// Where, as a JSON pointer into the comparison document.
    pub pointer: String,
    /// What.
    pub message: String,
}

/// A normalized side. Outside this crate it is built only by [`Normalizer::normalize`]
/// and [`Normalized::stored`] (it is non-exhaustive), so that no caller can pass a stored
/// document to the comparator without the fixed-point check.
#[derive(Debug, Clone, PartialEq)]
#[non_exhaustive]
pub struct Normalized {
    /// Which side it is.
    pub side: Side,
    /// The comparison document.
    pub document: Value,
    /// Every replacement made, in order (at most [`MAX_APPLIED`]).
    pub applied: Vec<Applied>,
    /// More replacements were made than [`MAX_APPLIED`].
    pub applied_truncated: bool,
    /// Problems found.
    pub issues: Vec<Issue>,
}

impl Normalized {
    /// A reference stored in its normalized form: the `document` of an earlier
    /// [`Normalizer::normalize`] of the reference side, read back. `ctx` is the context
    /// the reference was recorded with. The document is refused, with the pointer of the
    /// offending value, unless it is a comparison document that is a fixed point of
    /// `normalizer` under `ctx` ([`Normalizer::check_stored`]): no header value, body,
    /// event, line, file or log line may hold a value that a list entry or a decided
    /// rename would still replace. Accepted, it is compared as it is; nothing is
    /// normalized again, so no placeholder check applies to it.
    pub fn stored(
        document: Value,
        normalizer: &Normalizer,
        ctx: &SideContext,
    ) -> Result<Self, NormalizeError> {
        normalizer.check_stored(&document, ctx)?;
        Ok(Self {
            side: Side::Reference,
            document,
            applied: Vec::new(),
            applied_truncated: false,
            issues: Vec::new(),
        })
    }
}

#[derive(Debug, Clone)]
enum Loc {
    Header(String),
    /// The `Content-Length` header, whose value is derived from the normalized body.
    ContentLength,
    JsonKey {
        key: String,
        parent: Option<String>,
        top_level: bool,
        value_type: Option<String>,
    },
    IdPrefix {
        prefix: String,
        hex_digits: u64,
    },
    Metric(String),
    FileName(Pattern),
    LogText {
        reference: Pattern,
        candidate: Pattern,
    },
}

#[derive(Debug, Clone)]
struct Field {
    id: String,
    class: VolatileClass,
    loc: Loc,
}

/// The normalizer for one volatile-field list and one rename map.
#[derive(Debug, Clone)]
pub struct Normalizer {
    fields: Vec<Field>,
    renames: RenameMap,
}

impl Normalizer {
    /// Builds a normalizer. Fails when an entry of `fields` has a location the
    /// normalizer cannot apply with its class, or a pattern with an unknown hole. The
    /// class `body-length` applies to the `Content-Length` header only, and that header
    /// takes no other class: its value is derived, never a free placeholder.
    pub fn new(fields: &VolatileFields, renames: RenameMap) -> Result<Self, NormalizeError> {
        let mut out = Vec::new();
        for (i, f) in fields.fields.iter().enumerate() {
            let ptr = format!("/fields/{i}");
            let bad = |what: &str| err(&ptr, format!("{}: {what}", f.id));
            use VolatileClass as C;
            let loc = match (&f.location, f.class) {
                (Location::Header { name }, C::HeaderValue)
                    if !name.eq_ignore_ascii_case("content-length") =>
                {
                    Loc::Header(name.clone())
                }
                (Location::Header { name }, C::BodyLength)
                    if name.eq_ignore_ascii_case("content-length") =>
                {
                    Loc::ContentLength
                }
                (
                    Location::JsonKey {
                        key,
                        parent,
                        top_level,
                        value_type,
                    },
                    C::EpochS | C::EpochFloat | C::Iso | C::Num | C::Port | C::TmpPath,
                ) => {
                    if *top_level && parent.is_some() {
                        return Err(bad("a top-level location has no parent"));
                    }
                    Loc::JsonKey {
                        key: key.clone(),
                        parent: parent.clone(),
                        top_level: *top_level,
                        value_type: value_type.clone(),
                    }
                }
                (Location::IdPrefix { prefix, hex_digits }, C::Id) => Loc::IdPrefix {
                    prefix: prefix.clone(),
                    hex_digits: *hex_digits,
                },
                (Location::Metric { name }, C::Num) => Loc::Metric(name.clone()),
                (Location::FileName { pattern }, C::Id | C::Pid) => {
                    let p = Pattern::compile(pattern).map_err(|e| bad(&e))?;
                    let want = |h: &Hole| match f.class {
                        C::Id => matches!(h, Hole::Hex(_)),
                        _ => matches!(h, Hole::Pid),
                    };
                    let holes: Vec<&Hole> = p
                        .pieces
                        .iter()
                        .filter_map(|x| match x {
                            Piece::Hole(h) => Some(h),
                            Piece::Literal(_) => None,
                        })
                        .collect();
                    if holes.len() != 1 || !holes.iter().all(|h| want(h)) {
                        return Err(bad("a file-name pattern has exactly one hole of its class"));
                    }
                    Loc::FileName(p)
                }
                (Location::LogText { pattern }, C::Port | C::TmpPath | C::Num) => {
                    let p = Pattern::compile(pattern).map_err(|e| bad(&e))?;
                    let holes: Vec<Hole> = p
                        .pieces
                        .iter()
                        .filter_map(|x| match x {
                            Piece::Hole(h) => Some(*h),
                            Piece::Literal(_) => None,
                        })
                        .collect();
                    let ok = match f.class {
                        C::Port => holes.contains(&Hole::Port) && !holes.contains(&Hole::Num),
                        C::Num => !holes.is_empty() && holes.iter().all(|h| *h == Hole::Num),
                        _ => {
                            p.pieces.len() == 2 && p.pieces.get(1) == Some(&Piece::Hole(Hole::Rand))
                        }
                    };
                    if !ok {
                        return Err(bad(
                            "a log-text port pattern has a <port> hole and no <num> hole; a figure pattern has only <num> holes; a temporary-path pattern is a prefix then <rand>",
                        ));
                    }
                    let candidate = match renames.apply("tmp-prefix", p.lead()) {
                        Some(new) if f.class == C::TmpPath => {
                            Pattern::compile(&format!("{new}<rand>")).map_err(|e| bad(&e))?
                        }
                        _ => p.clone(),
                    };
                    Loc::LogText {
                        reference: p,
                        candidate,
                    }
                }
                (loc, class) => {
                    return Err(bad(&format!(
                        "class {} cannot be applied at a {} location",
                        class.as_str(),
                        loc_kind(loc)
                    )))
                }
            };
            out.push(Field {
                id: f.id.clone(),
                class: f.class,
                loc,
            });
        }
        Ok(Self {
            fields: out,
            renames,
        })
    }

    /// The rename map this normalizer applies.
    pub fn renames(&self) -> &RenameMap {
        &self.renames
    }

    /// The ids of the list entries it applies, in list order.
    pub fn field_ids(&self) -> impl Iterator<Item = &str> {
        self.fields.iter().map(|f| f.id.as_str())
    }

    /// Normalizes an observation recorded in this process.
    pub fn normalize_observation(
        &self,
        observation: &Observation,
        side: Side,
        ctx: &SideContext,
    ) -> Result<Normalized, NormalizeError> {
        self.normalize(&observation.to_json(), side, ctx)
    }

    /// Normalizes an observation document, in the shape
    /// [`Observation::to_json`] writes (for example a committed reference).
    pub fn normalize(
        &self,
        observation: &Value,
        side: Side,
        ctx: &SideContext,
    ) -> Result<Normalized, NormalizeError> {
        let mut run = Run {
            n: self,
            side,
            ctx,
            ids: BTreeMap::new(),
            applied: Vec::new(),
            applied_truncated: false,
            issues: Vec::new(),
        };
        let document = run.observation(observation)?;
        Ok(Normalized {
            side,
            document,
            applied: run.applied,
            applied_truncated: run.applied_truncated,
            issues: run.issues,
        })
    }

    fn content_length_field(&self) -> Option<&Field> {
        self.fields
            .iter()
            .find(|f| matches!(f.loc, Loc::ContentLength))
    }
}

fn loc_kind(loc: &Location) -> &'static str {
    match loc {
        Location::Header { .. } => "header",
        Location::JsonKey { .. } => "json-key",
        Location::IdPrefix { .. } => "id-prefix",
        Location::Metric { .. } => "metric",
        Location::FileName { .. } => "file-name",
        Location::LogText { .. } => "log-text",
    }
}

/// The prefix an id of a file-name pattern is numbered under: the literal text right
/// before its hex hole (`req-` for `req-<hex12>.dsi`). The placeholder check probes the
/// same prefix, so both always agree.
fn id_hole_prefix(p: &Pattern) -> String {
    p.pieces
        .windows(2)
        .find_map(|w| match w {
            [Piece::Literal(s), Piece::Hole(Hole::Hex(_))] => Some(s.clone()),
            _ => None,
        })
        .unwrap_or_default()
}

/// Escapes one JSON pointer segment.
pub fn pointer_segment(s: &str) -> String {
    s.replace('~', "~0").replace('/', "~1")
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Edit {
    start: usize,
    end: usize,
    text: String,
}

fn apply_edits(text: &str, mut edits: Vec<Edit>) -> String {
    edits.sort_by_key(|e| (e.start, e.end));
    let mut out = String::with_capacity(text.len());
    let mut at = 0;
    for e in edits {
        if e.start < at || e.end < e.start {
            continue;
        }
        let (Some(keep), true) = (text.get(at..e.start), text.get(e.start..e.end).is_some()) else {
            continue;
        };
        out.push_str(keep);
        out.push_str(&e.text);
        at = e.end;
    }
    out.push_str(text.get(at..).unwrap_or_default());
    out
}

/// One side's normalization in progress.
struct Run<'a> {
    n: &'a Normalizer,
    side: Side,
    ctx: &'a SideContext,
    /// Id numbering by first appearance across the scenario: prefix, then id, then k.
    ids: BTreeMap<String, BTreeMap<String, usize>>,
    applied: Vec<Applied>,
    applied_truncated: bool,
    issues: Vec<Issue>,
}

/// The JSON type a location's `value_type` names.
fn type_matches(want: Option<&str>, node: &Node, text: &str) -> bool {
    match (want, node) {
        (None, _) => true,
        (Some("string"), Node::String { .. }) => true,
        (Some("number"), Node::Number { .. }) => true,
        (Some("integer"), Node::Number { span }) => text
            .get(span.0..span.1)
            .is_some_and(|l| !l.bytes().any(|c| matches!(c, b'.' | b'e' | b'E'))),
        _ => false,
    }
}

impl<'a> Run<'a> {
    fn record(&mut self, source: String, pointer: String) {
        if self.applied.len() < MAX_APPLIED {
            self.applied.push(Applied { source, pointer });
        } else {
            self.applied_truncated = true;
        }
    }

    fn issue(&mut self, pointer: &str, message: impl Into<String>) {
        self.issues.push(Issue {
            pointer: pointer.to_string(),
            message: message.into(),
        });
    }

    /// The name a donor name has on this side: the reference keeps it; the candidate
    /// takes the rename map's applicable value in `scope`, when there is one.
    fn side_name(&self, scope: &str, donor: &str) -> String {
        match self.side {
            Side::Reference => donor.to_string(),
            Side::Candidate => self
                .n
                .renames
                .apply(scope, donor)
                .unwrap_or_else(|| donor.to_string()),
        }
    }

    fn id_placeholder(&mut self, prefix: &str, id: &str) -> String {
        let by_id = self.ids.entry(prefix.to_string()).or_default();
        let next = by_id.len() + 1;
        let k = *by_id.entry(id.to_string()).or_insert(next);
        format!("<{prefix}#{k}>")
    }

    /// Records an issue when `text` already holds a placeholder, which would make an
    /// observed value indistinguishable from a normalized one.
    fn check_placeholders(&mut self, text: &str, pointer: &str) {
        let mut hits: Vec<String> = PLACEHOLDERS
            .iter()
            .filter(|p| text.contains(**p))
            .map(|p| (*p).to_string())
            .collect();
        for f in &self.n.fields {
            let prefix = match &f.loc {
                Loc::IdPrefix { prefix, .. } => prefix.clone(),
                Loc::FileName(p) if f.class == VolatileClass::Id => id_hole_prefix(p),
                _ => continue,
            };
            let probe = format!("<{prefix}#");
            if text.contains(&probe) {
                hits.push(probe);
            }
        }
        if !hits.is_empty() {
            self.issue(
                pointer,
                format!("the observed text already holds placeholder text {hits:?}"),
            );
        }
    }

    /// Numbers the ids a request body holds before the response of its exchange is read.
    /// The donor keeps an id the client supplies (project-maya serve/responses.py:133,
    /// `item.setdefault("id", ...)`, and the echoed input items and
    /// `previous_response_id` at serve/responses.py:362 at 7e68a30f), so a client id has
    /// its own number, and a server that answers with a fresh id in its place shows a
    /// different one. The request itself stays out of the comparison document.
    fn request_ids(&mut self, request: &[u8]) {
        let Some(at) = request.windows(4).position(|w| w == b"\r\n\r\n") else {
            return;
        };
        let Some(text) = request
            .get(at + 4..)
            .and_then(|b| std::str::from_utf8(b).ok())
        else {
            return;
        };
        if text.is_empty() || text.len() > MAX_TEXT_BYTES {
            return;
        }
        if let Some(node) = json_text::scan(text) {
            self.collect_ids(&node);
        }
    }

    fn collect_ids(&mut self, node: &Node) {
        match node {
            Node::Object(members) => {
                for (_, v) in members {
                    self.collect_ids(v);
                }
            }
            Node::Array(items) => {
                for v in items {
                    self.collect_ids(v);
                }
            }
            Node::String {
                value, plain: true, ..
            } => {
                let n: &'a Normalizer = self.n;
                if let Some(prefix) = n.fields.iter().find_map(|f| match &f.loc {
                    Loc::IdPrefix { prefix, hex_digits }
                        if classes::is_id(value, prefix, *hex_digits) =>
                    {
                        Some(prefix)
                    }
                    _ => None,
                }) {
                    self.id_placeholder(prefix, value);
                }
            }
            _ => {}
        }
    }

    // ------------------------------------------------------------------ the document

    fn observation(&mut self, v: &Value) -> Result<Value, NormalizeError> {
        let obj = v.as_object().ok_or_else(|| err("", "not an object"))?;
        let mut out = Map::new();
        let http = obj
            .get("http")
            .and_then(Value::as_array)
            .ok_or_else(|| err("/http", "not an array"))?;
        let mut exchanges = Vec::new();
        for (i, ex) in http.iter().enumerate() {
            exchanges.push(self.exchange(ex, &format!("/http/{i}"))?);
        }
        out.insert("http".into(), Value::Array(exchanges));
        out.insert(
            "engine_tape".into(),
            obj.get("engine_tape").cloned().unwrap_or(Value::Null),
        );
        let files = match obj.get("files") {
            None | Some(Value::Null) => Vec::new(),
            Some(Value::Array(a)) => a.clone(),
            Some(_) => return Err(err("/files", "not an array")),
        };
        out.insert("files".into(), self.files(&files)?);
        let mut log = Vec::new();
        if let Some(lines) = obj.get("log") {
            let lines = lines
                .as_array()
                .ok_or_else(|| err("/log", "not an array"))?;
            for (i, l) in lines.iter().enumerate() {
                let ptr = format!("/log/{i}");
                let s = l.as_str().ok_or_else(|| err(&ptr, "not a string"))?;
                log.push(Value::String(self.log_line(s, &ptr)));
            }
        }
        out.insert("log".into(), Value::Array(log));
        out.insert(
            "exit".into(),
            obj.get("exit").cloned().unwrap_or(Value::Null),
        );
        Ok(Value::Object(out))
    }

    fn exchange(&mut self, ex: &Value, ptr: &str) -> Result<Value, NormalizeError> {
        let o = ex.as_object().ok_or_else(|| err(ptr, "not an object"))?;
        let get = |k: &str| {
            o.get(k)
                .ok_or_else(|| err(&format!("{ptr}/{k}"), "missing"))
        };
        let (request, _) = bytes_of(get("request")?, &format!("{ptr}/request"))?;
        self.request_ids(&request);
        let sent = get("request_sent")?
            .as_u64()
            .ok_or_else(|| err(&format!("{ptr}/request_sent"), "not a count"))?;
        let mut out = Map::new();
        out.insert(
            "request_complete".into(),
            Value::Bool(u64::try_from(request.len()).is_ok_and(|n| n == sent)),
        );
        out.insert("write_error".into(), get("write_error")?.clone());

        let mut raw_heads: Vec<u8> = Vec::new();
        let mut interim = Vec::new();
        for (i, h) in get("interim")?
            .as_array()
            .ok_or_else(|| err(&format!("{ptr}/interim"), "not an array"))?
            .iter()
            .enumerate()
        {
            let hp = format!("{ptr}/interim/{i}");
            let (raw, _) = bytes_of(h.get("raw").unwrap_or(&Value::Null), &format!("{hp}/raw"))?;
            raw_heads.extend_from_slice(&raw);
            interim.push(self.head(h, &hp)?);
        }
        out.insert("interim".into(), Value::Array(interim));
        let head_v = get("head")?;
        let mut head = if head_v.is_null() {
            Value::Null
        } else {
            let (raw, _) = bytes_of(
                head_v.get("raw").unwrap_or(&Value::Null),
                &format!("{ptr}/head/raw"),
            )?;
            raw_heads.extend_from_slice(&raw);
            self.head(head_v, &format!("{ptr}/head"))?
        };

        let (body, body_text) = bytes_of(get("body")?, &format!("{ptr}/body"))?;
        let kind = get("content")?
            .get("kind")
            .and_then(Value::as_str)
            .ok_or_else(|| err(&format!("{ptr}/content/kind"), "missing"))?
            .to_string();
        let media = head_media_type(head_v);
        let bp = format!("{ptr}/body");
        let new_body: Vec<u8> = match &body_text {
            Some(text) if text.len() <= MAX_TEXT_BYTES => {
                self.check_placeholders(text, &bp);
                let edits = match kind.as_str() {
                    "json" => self.json_edits(text, &bp),
                    "sse" => self.sse_edits(text, &body, &bp),
                    "ndjson" => self.ndjson_edits(text, &bp),
                    "opaque" if media.as_deref() == Some("text/plain") => {
                        self.metric_edits(text, &bp)
                    }
                    _ => Vec::new(),
                };
                apply_edits(text, edits).into_bytes()
            }
            _ => body.clone(),
        };
        let content = derive_content(&kind, &new_body, &format!("{ptr}/content"))?;

        let mut framing = get("framing")?.clone();
        let end = get("end")?.clone();
        let disconnect = get("disconnect")?;
        // only a close disconnect that ended the read leaves bytes past the body to the
        // client's timing; after a half-close the client reads on to the server's end
        let cut_by_client = disconnect.get("fired").and_then(Value::as_bool) == Some(true)
            && disconnect.get("mode").and_then(Value::as_str) == Some("close")
            && end.get("kind").and_then(Value::as_str) == Some("disconnected");
        self.content_length(
            &mut head,
            &mut framing,
            body.len(),
            new_body.len(),
            end.get("kind").and_then(Value::as_str) == Some("complete"),
            ptr,
        );
        out.insert("head".into(), head);
        out.insert("framing".into(), framing.clone());
        out.insert("body".into(), bytes_value(&new_body));
        out.insert("content".into(), content);
        out.insert("end".into(), end);
        out.insert("server_closed".into(), get("server_closed")?.clone());

        let mut d = disconnect.clone();
        if let Some(m) = d.as_object_mut() {
            m.remove("wire_bytes");
        }
        out.insert("disconnect".into(), d);

        let (wire, _) = bytes_of(get("wire")?, &format!("{ptr}/wire"))?;
        let mut prefix = raw_heads;
        prefix.extend_from_slice(&body);
        let chunked = framing.get("kind").and_then(Value::as_str) == Some("chunked");
        let consistent = !chunked
            && wire.starts_with(&prefix)
            && (wire.len() == prefix.len() || cut_by_client)
            && sha256_hex(wire.get(..prefix.len()).unwrap_or_default()) == sha256_hex(&prefix);
        out.insert(
            "wire".into(),
            if consistent {
                Value::String("consistent".into())
            } else {
                bytes_value(&wire)
            },
        );
        Ok(Value::Object(out))
    }

    fn head(&mut self, h: &Value, ptr: &str) -> Result<Value, NormalizeError> {
        let o = h.as_object().ok_or_else(|| err(ptr, "not an object"))?;
        let mut out = Map::new();
        for k in ["version", "code", "reason"] {
            out.insert(
                k.into(),
                o.get(k)
                    .cloned()
                    .ok_or_else(|| err(&format!("{ptr}/{k}"), "missing"))?,
            );
        }
        let headers = o
            .get("headers")
            .and_then(Value::as_array)
            .ok_or_else(|| err(&format!("{ptr}/headers"), "not an array"))?;
        let mut pairs: Vec<(String, String)> = Vec::new();
        for (i, pair) in headers.iter().enumerate() {
            let hp = format!("{ptr}/headers/{i}");
            let (Some(name), Some(value)) = (
                pair.get(0).and_then(Value::as_str),
                pair.get(1).and_then(Value::as_str),
            ) else {
                return Err(err(&hp, "not a [name, value] pair"));
            };
            if pair.as_array().map(Vec::len) != Some(2) {
                return Err(err(&hp, "not a [name, value] pair"));
            }
            self.check_placeholders(name, &hp);
            self.check_placeholders(value, &hp);
            pairs.push((name.to_string(), value.to_string()));
        }
        let (raw, raw_text) =
            bytes_of(o.get("raw").unwrap_or(&Value::Null), &format!("{ptr}/raw"))?;
        let mut raw_text = raw_text;
        if let Some(t) = &raw_text {
            self.check_placeholders(t, &format!("{ptr}/raw"));
        }
        let n: &'a Normalizer = self.n;
        for f in &n.fields {
            // the Content-Length value is derived from the body (`content_length`), and
            // `Normalizer::new` gives that header no other class
            let Loc::Header(name) = &f.loc else { continue };
            let at: Vec<usize> = pairs
                .iter()
                .enumerate()
                .filter(|(_, (n, _))| n.eq_ignore_ascii_case(name))
                .map(|(i, _)| i)
                .collect();
            let [i] = at.as_slice() else { continue };
            let Some(pair) = pairs.get_mut(*i) else {
                continue;
            };
            if pair.1.is_empty() {
                continue;
            }
            // Date: only the moment is volatile, not the form (parity-ledger.md 1.1)
            if name.eq_ignore_ascii_case("date") {
                let w = self.ctx.window;
                if !classes::imf_fixdate(&pair.1).is_some_and(|t| w.contains(t, 0.0)) {
                    continue;
                }
            }
            pair.1 = "<header>".into();
            self.record(format!("volatile:{}", f.id), format!("{ptr}/headers/{i}/1"));
            if let Some(t) = raw_text.take() {
                match raw_header_value(&t, name) {
                    Some((s, e)) => {
                        raw_text = Some(apply_edits(
                            &t,
                            vec![Edit {
                                start: s,
                                end: e,
                                text: "<header>".into(),
                            }],
                        ));
                        self.record(format!("volatile:{}", f.id), format!("{ptr}/raw"));
                    }
                    None => raw_text = Some(t),
                }
            }
        }
        out.insert(
            "headers".into(),
            Value::Array(pairs.into_iter().map(|(n, v)| json!([n, v])).collect()),
        );
        out.insert(
            "raw".into(),
            match raw_text {
                Some(t) => json!({ "text": t }),
                None => bytes_value(&raw),
            },
        );
        Ok(Value::Object(out))
    }

    /// The `Content-Length` value, when the list names it (class `body-length`, lead
    /// decision LD44), is re-derived from the normalized body: only when the read was
    /// complete, the framing says Content-Length with the length of the body received,
    /// the header is present once and its value is exactly the decimal length of the
    /// body received. Otherwise it is compared exactly. The header's name, case and
    /// position are never touched.
    ///
    /// Behavior reference: project-maya serve/server.py:5457-5463 at 7e68a30f (`_json`
    /// writes `str(len(body))` of the body it sends; so do 5665, 5999, 6084 and 6264).
    fn content_length(
        &mut self,
        head: &mut Value,
        framing: &mut Value,
        old_len: usize,
        new_len: usize,
        complete: bool,
        ptr: &str,
    ) {
        let Some(field) = self.n.content_length_field() else {
            return;
        };
        let id = field.id.clone();
        let framed = framing.get("kind").and_then(Value::as_str) == Some("content-length")
            && framing.get("length").and_then(Value::as_u64) == u64::try_from(old_len).ok();
        if !complete || !framed || old_len == new_len {
            return;
        }
        let Some(headers) = head.get_mut("headers").and_then(Value::as_array_mut) else {
            return;
        };
        let at: Vec<usize> = headers
            .iter()
            .enumerate()
            .filter(|(_, p)| {
                p.get(0)
                    .and_then(Value::as_str)
                    .is_some_and(|n| n.eq_ignore_ascii_case("content-length"))
            })
            .map(|(i, _)| i)
            .collect();
        let [i] = at.as_slice() else { return };
        let old = old_len.to_string();
        let new = new_len.to_string();
        let Some(slot) = headers.get_mut(*i).and_then(|p| p.get_mut(1)) else {
            return;
        };
        if slot.as_str() != Some(old.as_str()) {
            return;
        }
        *slot = Value::String(new.clone());
        self.record(
            format!("volatile:{id}"),
            format!("{ptr}/head/headers/{i}/1"),
        );
        if let Some(raw) = head.get_mut("raw") {
            if let Some(t) = raw.get("text").and_then(Value::as_str).map(str::to_string) {
                if let Some((s, e)) = raw_header_value(&t, "content-length") {
                    if t.get(s..e) == Some(old.as_str()) {
                        let edited = apply_edits(
                            &t,
                            vec![Edit {
                                start: s,
                                end: e,
                                text: new.clone(),
                            }],
                        );
                        *raw = json!({ "text": edited });
                    }
                }
            }
        }
        if let Some(m) = framing.as_object_mut() {
            m.insert("length".into(), json!(new_len));
        }
    }

    // ------------------------------------------------------------------ JSON text

    /// Edits for one JSON document; none when it does not scan.
    fn json_edits(&mut self, text: &str, ptr: &str) -> Vec<Edit> {
        let mut edits = Vec::new();
        if text.len() > MAX_TEXT_BYTES {
            return edits;
        }
        if let Some(node) = json_text::scan(text) {
            let mut path = Vec::new();
            self.walk(&node, text, None, None, false, &mut path, ptr, &mut edits);
        }
        edits
    }

    #[allow(clippy::too_many_arguments)]
    fn walk(
        &mut self,
        node: &Node,
        text: &str,
        key: Option<&str>,
        parent: Option<&str>,
        model_alias: bool,
        path: &mut Vec<String>,
        ptr: &str,
        edits: &mut Vec<Edit>,
    ) {
        match node {
            Node::Object(members) => {
                let model = members.iter().find_map(|(k, v)| match (k.as_str(), v) {
                    ("model", Node::String { value, .. }) => Some(value.as_str()),
                    _ => None,
                });
                for (k, v) in members {
                    // a `name` that repeats its object's `model` is the same public name
                    let alias = k == "name"
                        && matches!(v, Node::String { value, .. } if Some(value.as_str()) == model);
                    path.push(pointer_segment(k));
                    self.walk(v, text, Some(k), key, alias, path, ptr, edits);
                    path.pop();
                }
            }
            Node::Array(items) => {
                for (i, v) in items.iter().enumerate() {
                    path.push(i.to_string());
                    self.walk(v, text, None, None, false, path, ptr, edits);
                    path.pop();
                }
            }
            Node::Literal => {}
            leaf => {
                let at = format!("{ptr}#/{}", path.join("/"));
                // a member of the document's root object: one segment, and that one a key
                let top = path.len() == 1 && key.is_some();
                if let Some(e) = self.leaf(leaf, text, key, parent, top, model_alias, &at) {
                    edits.push(e);
                }
            }
        }
    }

    /// The list entry for a member named `key`, a member of an object that is the value
    /// of `parent` (when any), of the root object when `top`. An entry with a parent or
    /// limited to the root object is preferred to one that applies at any depth.
    fn json_key_field(
        &self,
        key: &str,
        parent: Option<&str>,
        top: bool,
        node: &Node,
        text: &str,
    ) -> Option<&'a Field> {
        let n: &'a Normalizer = self.n;
        let candidates = n.fields.iter().filter(|f| match &f.loc {
            Loc::JsonKey {
                key: k,
                parent: p,
                top_level,
                value_type,
            } => {
                self.side_name("json-key", k) == key
                    && p.as_deref()
                        .is_none_or(|p| Some(self.side_name("json-key", p).as_str()) == parent)
                    && (!*top_level || top)
                    && type_matches(value_type.as_deref(), node, text)
            }
            _ => false,
        });
        let specific = |f: &Field| {
            matches!(
                &f.loc,
                Loc::JsonKey {
                    parent: Some(_),
                    ..
                } | Loc::JsonKey {
                    top_level: true,
                    ..
                }
            )
        };
        let mut best: Option<&'a Field> = None;
        for f in candidates {
            match best {
                None => best = Some(f),
                Some(b) if specific(f) && !specific(b) => best = Some(f),
                _ => {}
            }
        }
        best
    }

    #[allow(clippy::too_many_arguments)]
    fn leaf(
        &mut self,
        node: &Node,
        text: &str,
        key: Option<&str>,
        parent: Option<&str>,
        top: bool,
        model_alias: bool,
        at: &str,
    ) -> Option<Edit> {
        let (span, lexeme) = match node {
            Node::Number { span } | Node::String { span, .. } => (*span, text.get(span.0..span.1)?),
            _ => return None,
        };
        let quoted = |s: &str| format!("\"{s}\"");
        if let Some(k) = key {
            if let Some(f) = self.json_key_field(k, parent, top, node, text) {
                let id = f.id.clone();
                let ext = self.ctx.extension(&id);
                let w = self.ctx.window;
                let replacement = match (f.class, node) {
                    (VolatileClass::EpochS, Node::Number { .. }) => classes::epoch(lexeme)
                        .filter(|(s, t)| *s == Shape::Integer && w.contains(*t, ext))
                        .map(|_| quoted("<epoch-s>")),
                    (VolatileClass::EpochFloat, Node::Number { .. }) => classes::epoch(lexeme)
                        .filter(|(_, t)| w.contains(*t, ext))
                        .map(|(s, _)| quoted(&format!("<epoch-s{}>", s.suffix()))),
                    (VolatileClass::Num, Node::Number { .. }) => {
                        classes::non_negative_number(lexeme)
                            .map(|(s, _)| quoted(&format!("<num{}>", s.suffix())))
                    }
                    (VolatileClass::Port, Node::Number { .. }) => {
                        classes::port(lexeme, self.ctx.port).then(|| quoted("{{port}}"))
                    }
                    (
                        VolatileClass::Iso,
                        Node::String {
                            value, plain: true, ..
                        },
                    ) => classes::iso_utc(value)
                        .filter(|t| w.contains(*t, ext))
                        .map(|_| quoted("<iso>")),
                    (
                        VolatileClass::TmpPath,
                        Node::String {
                            value, plain: true, ..
                        },
                    ) => {
                        match classes::under_tmp(value, &self.ctx.tmp_dirs) {
                            Some(n) => {
                                // the file name at the end of the path takes the reference
                                // side's `file` rename, as an observed file path does
                                let (rest, sources) =
                                    self.rename_path(value.get(n..).unwrap_or_default());
                                for s in sources {
                                    self.record(format!("rename:{s}"), at.to_string());
                                }
                                Some(format!("{{{{tmp}}}}{rest}"))
                                    .filter(|t| is_plain_json_content(t))
                                    .map(|t| quoted(&t))
                            }
                            None => None,
                        }
                    }
                    _ => None,
                };
                return replacement.map(|t| {
                    self.record(format!("volatile:{id}"), at.to_string());
                    Edit {
                        start: span.0,
                        end: span.1,
                        text: t,
                    }
                });
            }
        }
        let Node::String {
            value, plain: true, ..
        } = node
        else {
            return None;
        };
        let n: &'a Normalizer = self.n;
        for f in &n.fields {
            let Loc::IdPrefix { prefix, hex_digits } = &f.loc else {
                continue;
            };
            if classes::is_id(value, prefix, *hex_digits) {
                let (id, prefix) = (f.id.clone(), prefix.clone());
                let placeholder = self.id_placeholder(&prefix, value);
                self.record(format!("volatile:{id}"), at.to_string());
                return Some(Edit {
                    start: span.0,
                    end: span.1,
                    text: quoted(&placeholder),
                });
            }
        }
        if self.side == Side::Reference {
            let rename_key = if model_alias { Some("model") } else { key };
            let (renamed, sources) = self.rename_string(value, rename_key);
            if renamed != *value && is_plain_json_content(&renamed) {
                for s in sources {
                    self.record(format!("rename:{s}"), at.to_string());
                }
                return Some(Edit {
                    start: span.0,
                    end: span.1,
                    text: quoted(&renamed),
                });
            }
        }
        None
    }

    /// The reference-side renames of a JSON string: `model-name` for the value of a
    /// `model` member (or of a `name` that repeats it), `file` for a bare file name in a
    /// `file` or `to` member, `text` for a whole string, `env` for variable names inside
    /// it.
    ///
    /// Behavior reference: project-maya serve/server.py:3101, 3107 and 3159 and
    /// serve/model_api.py:92 at 7e68a30f (`"file": p.name`, `"to": p.name`).
    fn rename_string(&self, value: &str, key: Option<&str>) -> (String, Vec<String>) {
        let mut sources = Vec::new();
        let mut s = value.to_string();
        if matches!(key, Some("file" | "to")) && !s.contains('/') {
            if let Some(e) = self
                .n
                .renames
                .applicable()
                .find(|e| e.scope == "file" && e.apply(&s).is_some())
            {
                if let Some(new) = e.apply(&s) {
                    sources.push(e.deviation.clone());
                    s = new;
                }
            }
        }
        if key == Some("model") {
            if let Some(e) = self
                .n
                .renames
                .applicable()
                .find(|e| e.scope == "model-name" && e.apply(&s).is_some())
            {
                if let Some(new) = e.apply(&s) {
                    sources.push(e.deviation.clone());
                    s = new;
                }
            }
        }
        if let Some(e) = self
            .n
            .renames
            .applicable()
            .find(|e| e.scope == "text" && e.apply(&s).is_some())
        {
            if let Some(new) = e.apply(&s) {
                sources.push(e.deviation.clone());
                s = new;
            }
        }
        let (env, env_sources) = self.rename_env_words(&s);
        sources.extend(env_sources);
        (env, sources)
    }

    /// Replaces each exact `env` name of the map found in `s` as a whole word (not next
    /// to a letter, digit or underscore).
    fn rename_env_words(&self, s: &str) -> (String, Vec<String>) {
        let mut out = s.to_string();
        let mut sources = Vec::new();
        for e in self
            .n
            .renames
            .applicable()
            .filter(|e| e.scope == "env" && e.matching == crate::scenario::Match::Exact)
        {
            let Some(new) = e.new.as_deref() else {
                continue;
            };
            if e.old.is_empty() || !out.contains(&e.old) {
                continue;
            }
            let mut result = String::with_capacity(out.len());
            let mut rest = out.as_str();
            let mut changed = false;
            let mut prev: Option<char> = None;
            while let Some(i) = rest.find(&e.old) {
                let before = rest.get(..i).unwrap_or_default();
                let left = before.chars().next_back().or(prev);
                let after = rest.get(i + e.old.len()..).unwrap_or_default();
                let right = after.chars().next();
                let word =
                    |c: Option<char>| c.is_some_and(|c| c.is_ascii_alphanumeric() || c == '_');
                result.push_str(before);
                if !word(left) && !word(right) {
                    result.push_str(new);
                    changed = true;
                } else {
                    result.push_str(&e.old);
                }
                prev = e.old.chars().next_back();
                rest = after;
            }
            result.push_str(rest);
            if changed {
                sources.push(e.deviation.clone());
                out = result;
            }
        }
        (out, sources)
    }

    // ------------------------------------------------------------------ streams

    /// Edits for an event stream: the `data` lines of each event, joined as the
    /// event-stream format joins them, are one JSON document when they scan.
    fn sse_edits(&mut self, text: &str, body: &[u8], ptr: &str) -> Vec<Edit> {
        let mut parser = SseParser::new();
        parser.feed(body, None);
        let stream = parser.finish();
        let mut edits = Vec::new();
        let mut cursor = 0;
        for (k, ev) in stream.events.iter().enumerate() {
            let Ok(raw) = std::str::from_utf8(&ev.raw) else {
                continue;
            };
            let Some(at) = find_at_line_start(text, raw, cursor) else {
                continue;
            };
            cursor = at + raw.len();
            let lines = sse_data_lines(raw, at);
            if lines.is_empty() {
                continue;
            }
            let mut joined = String::new();
            let mut segments = Vec::new();
            for (i, (abs, value)) in lines.iter().enumerate() {
                if i > 0 {
                    joined.push('\n');
                }
                segments.push((joined.len(), *abs, value.len()));
                joined.push_str(value);
            }
            for e in self.json_edits(&joined, &format!("{ptr}/events/{k}")) {
                let seg = segments
                    .iter()
                    .find(|(j, _, len)| *j <= e.start && e.end <= j + len);
                if let Some((j, abs, _)) = seg {
                    edits.push(Edit {
                        start: abs + (e.start - j),
                        end: abs + (e.end - j),
                        text: e.text,
                    });
                }
            }
        }
        edits
    }

    fn ndjson_edits(&mut self, text: &str, ptr: &str) -> Vec<Edit> {
        let mut edits = Vec::new();
        let mut start = 0;
        let mut k = 0;
        while let Some(off) = text.get(start..).and_then(|t| t.find('\n')) {
            let line = text.get(start..start + off).unwrap_or_default();
            for e in self.json_edits(line, &format!("{ptr}/lines/{k}")) {
                edits.push(Edit {
                    start: start + e.start,
                    end: start + e.end,
                    text: e.text,
                });
            }
            start += off + 1;
            k += 1;
        }
        edits
    }

    /// Edits for a Prometheus text body: the value of each sample of a listed metric.
    ///
    /// Behavior reference: project-maya serve/server.py:3470-3471 at 7e68a30f (each
    /// sample is written as `<name> <value>`).
    fn metric_edits(&mut self, text: &str, ptr: &str) -> Vec<Edit> {
        let mut edits = Vec::new();
        let mut start = 0;
        for (k, line) in text.split('\n').enumerate() {
            let line_start = start;
            start += line.len() + 1;
            if line.starts_with('#') {
                continue;
            }
            let name_end = line.find([' ', '{']).unwrap_or(line.len());
            let name = line.get(..name_end).unwrap_or_default();
            let n: &'a Normalizer = self.n;
            let Some(f) = n.fields.iter().find(|f| match &f.loc {
                Loc::Metric(m) => self.side_name("metric", m) == name,
                _ => false,
            }) else {
                continue;
            };
            let id = f.id.clone();
            let mut v = name_end;
            if line.get(v..v + 1) == Some("{") {
                match line.get(v..).and_then(|t| t.find('}')) {
                    Some(close) => v += close + 1,
                    None => continue,
                }
            }
            if line.get(v..v + 1) != Some(" ") {
                continue;
            }
            v += 1;
            let value = line.get(v..).unwrap_or_default();
            if let Some((shape, _)) = classes::non_negative_number(value) {
                self.record(format!("volatile:{id}"), format!("{ptr}#line{k}"));
                edits.push(Edit {
                    start: line_start + v,
                    end: line_start + line.len(),
                    text: format!("<num{}>", shape.suffix()),
                });
            }
        }
        edits
    }

    // ------------------------------------------------------------------ files and log

    fn files(&mut self, files: &[Value]) -> Result<Value, NormalizeError> {
        let mut prepared = Vec::new();
        for (i, f) in files.iter().enumerate() {
            let fp = format!("/files/{i}");
            let path = f
                .get("path")
                .and_then(Value::as_str)
                .ok_or_else(|| err(&format!("{fp}/path"), "not a string"))?;
            let (bytes, text) = bytes_of(
                f.get("bytes").unwrap_or(&Value::Null),
                &format!("{fp}/bytes"),
            )?;
            let renamed = self.rename_path(path);
            // ids are numbered in this order, so it must not depend on the ids
            // themselves: the path and the content with every volatile hole and id masked
            let key = (
                self.mask_path(&renamed.0),
                match &text {
                    Some(t) if t.len() <= MAX_TEXT_BYTES => self.order_text(t).into_bytes(),
                    _ => bytes.clone(),
                },
            );
            prepared.push((key, renamed, path.to_string(), bytes, text));
        }
        prepared.sort_by(|a, b| a.0.cmp(&b.0));
        let mut out = Vec::new();
        for (_, (renamed, sources), original, bytes, text) in prepared {
            let ptr = format!("/files/{}", pointer_segment(&original));
            self.check_placeholders(&original, &ptr);
            for s in sources {
                self.record(format!("rename:{s}"), format!("{ptr}/path"));
            }
            let path = self.path_volatile(&renamed, &ptr);
            let new_bytes = match &text {
                Some(t) if t.len() <= MAX_TEXT_BYTES => {
                    self.check_placeholders(t, &format!("{ptr}/bytes"));
                    let edits = if json_text::scan(t).is_some() {
                        self.json_edits(t, &format!("{ptr}/bytes"))
                    } else {
                        self.ndjson_edits(t, &format!("{ptr}/bytes"))
                    };
                    apply_edits(t, edits).into_bytes()
                }
                _ => bytes,
            };
            let parsed: Option<Value> = serde_json::from_slice(&new_bytes).ok();
            let mut m = Map::new();
            m.insert("path".into(), Value::String(path));
            m.insert("bytes".into(), bytes_value(&new_bytes));
            m.insert("is_json".into(), Value::Bool(parsed.is_some()));
            m.insert("json".into(), parsed.unwrap_or(Value::Null));
            out.push(Value::Object(m));
        }
        out.sort_by(|a, b| {
            let pa = a.get("path").and_then(Value::as_str).unwrap_or_default();
            let pb = b.get("path").and_then(Value::as_str).unwrap_or_default();
            pa.cmp(pb)
        });
        Ok(Value::Array(out))
    }

    /// `path` with the hole of each segment that a `file-name` entry matches written as
    /// `#`: an ordering key only.
    fn mask_path(&self, path: &str) -> String {
        let mut out = Vec::new();
        for seg in path.split('/') {
            let masked = self.n.fields.iter().find_map(|f| match &f.loc {
                Loc::FileName(p) if p.match_whole(seg).is_some() => Some(
                    p.pieces
                        .iter()
                        .map(|x| match x {
                            Piece::Literal(s) => s.as_str(),
                            Piece::Hole(_) => "#",
                        })
                        .collect::<String>(),
                ),
                _ => None,
            });
            out.push(masked.unwrap_or_else(|| seg.to_string()));
        }
        out.join("/")
    }

    /// A file's text normalized on a scratch run (so nothing is recorded and no id takes
    /// a number), with every id number masked: an ordering key only, the same on both
    /// sides when the files agree apart from volatile values.
    fn order_text(&self, text: &str) -> String {
        let mut scratch = Run {
            n: self.n,
            side: self.side,
            ctx: self.ctx,
            ids: BTreeMap::new(),
            applied: Vec::new(),
            applied_truncated: false,
            issues: Vec::new(),
        };
        let edits = if json_text::scan(text).is_some() {
            scratch.json_edits(text, "")
        } else {
            scratch.ndjson_edits(text, "")
        };
        mask_id_numbers(&apply_edits(text, edits))
    }

    /// The reference side's file rename of the last path segment.
    fn rename_path(&self, path: &str) -> (String, Vec<String>) {
        if self.side != Side::Reference {
            return (path.to_string(), Vec::new());
        }
        let (dir, name) = match path.rfind('/') {
            Some(i) => (
                path.get(..=i).unwrap_or_default(),
                path.get(i + 1..).unwrap_or_default(),
            ),
            None => ("", path),
        };
        match self
            .n
            .renames
            .applicable()
            .find(|e| e.scope == "file" && e.apply(name).is_some())
        {
            Some(e) => match e.apply(name) {
                Some(new) => (format!("{dir}{new}"), vec![e.deviation.clone()]),
                None => (path.to_string(), Vec::new()),
            },
            None => (path.to_string(), Vec::new()),
        }
    }

    /// The `file-name` entries, applied to each segment of a path.
    fn path_volatile(&mut self, path: &str, ptr: &str) -> String {
        let mut segments = Vec::new();
        for seg in path.split('/') {
            let mut out = seg.to_string();
            let fields: Vec<Field> = self
                .n
                .fields
                .iter()
                .filter(|f| matches!(f.loc, Loc::FileName(_)))
                .cloned()
                .collect();
            for f in fields {
                let Loc::FileName(p) = &f.loc else { continue };
                let Some(caps) = p.match_whole(seg) else {
                    continue;
                };
                let mut rendered = String::new();
                let mut ok = true;
                for (i, piece) in p.pieces.iter().enumerate() {
                    match piece {
                        Piece::Literal(s) => {
                            let next_is_id = f.class == VolatileClass::Id
                                && matches!(p.pieces.get(i + 1), Some(Piece::Hole(Hole::Hex(_))));
                            if !next_is_id {
                                rendered.push_str(s);
                            }
                        }
                        Piece::Hole(h) => {
                            let Some(c) = caps.iter().find(|c| c.piece == i) else {
                                ok = false;
                                break;
                            };
                            let hole_text = seg.get(c.start..c.end).unwrap_or_default();
                            match (f.class, h) {
                                (VolatileClass::Id, Hole::Hex(_)) => {
                                    let prefix = id_hole_prefix(p);
                                    let id = format!("{prefix}{hole_text}");
                                    rendered.push_str(&self.id_placeholder(&prefix, &id));
                                }
                                (VolatileClass::Pid, Hole::Pid) if classes::pid(hole_text) => {
                                    rendered.push_str("<pid>");
                                }
                                _ => {
                                    ok = false;
                                    break;
                                }
                            }
                        }
                    }
                }
                if ok {
                    self.record(format!("volatile:{}", f.id), format!("{ptr}/path"));
                    out = rendered;
                    break;
                }
            }
            segments.push(out);
        }
        segments.join("/")
    }

    fn log_line(&mut self, line: &str, ptr: &str) -> String {
        if line.len() > MAX_TEXT_BYTES {
            return line.to_string();
        }
        self.check_placeholders(line, ptr);
        let mut edits = Vec::new();
        let fields: Vec<Field> = self
            .n
            .fields
            .iter()
            .filter(|f| matches!(f.loc, Loc::LogText { .. }))
            .cloned()
            .collect();
        for f in &fields {
            let Loc::LogText {
                reference,
                candidate,
            } = &f.loc
            else {
                continue;
            };
            let p = match self.side {
                Side::Reference => reference,
                Side::Candidate => candidate,
            };
            for ((start, end), caps) in p.find_all(line) {
                match f.class {
                    VolatileClass::Port => {
                        for c in caps.iter().filter(|c| c.hole == Hole::Port) {
                            let t = line.get(c.start..c.end).unwrap_or_default();
                            if classes::port(t, self.ctx.port) {
                                self.record(format!("volatile:{}", f.id), ptr.to_string());
                                edits.push(Edit {
                                    start: c.start,
                                    end: c.end,
                                    text: "{{port}}".into(),
                                });
                            }
                        }
                    }
                    VolatileClass::Num => {
                        // only the holes: the text around them, such as a token count
                        // before the pattern, stays observable
                        for c in caps.iter().filter(|c| c.hole == Hole::Num) {
                            let t = line.get(c.start..c.end).unwrap_or_default();
                            if let Some((shape, _)) = classes::non_negative_number(t) {
                                self.record(format!("volatile:{}", f.id), ptr.to_string());
                                edits.push(Edit {
                                    start: c.start,
                                    end: c.end,
                                    text: format!("<num{}>", shape.suffix()),
                                });
                            }
                        }
                    }
                    VolatileClass::TmpPath => {
                        let before = line.get(..start).unwrap_or_default();
                        let dir = self
                            .ctx
                            .tmp_dirs
                            .iter()
                            .map(|d| d.trim_end_matches('/'))
                            .filter(|d| !d.is_empty())
                            .find(|d| before.ends_with(&format!("{d}/")));
                        if let Some(d) = dir {
                            self.record(format!("volatile:{}", f.id), ptr.to_string());
                            edits.push(Edit {
                                start: start - d.len() - 1,
                                end,
                                text: format!("{{{{tmp}}}}/{}<rand>", p.lead()),
                            });
                        }
                    }
                    _ => {}
                }
            }
        }
        let mut out = apply_edits(line, edits);
        if self.side == Side::Reference {
            if let Some(e) = self
                .n
                .renames
                .applicable()
                .find(|e| e.scope == "log" && e.apply(&out).is_some())
            {
                if let Some(new) = e.apply(&out) {
                    self.record(format!("rename:{}", e.deviation), ptr.to_string());
                    out = new;
                }
            }
            let (renamed, sources) = self.rename_env_words(&out);
            for s in sources {
                self.record(format!("rename:{s}"), ptr.to_string());
            }
            out = renamed;
        }
        out
    }
}

/// `s` with the number of each id placeholder dropped (`<chatcmpl-#2>` becomes
/// `<chatcmpl-#>`).
fn mask_id_numbers(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut rest = s;
    while let Some(i) = rest.find('#') {
        out.push_str(rest.get(..=i).unwrap_or_default());
        let after = rest.get(i + 1..).unwrap_or_default();
        let digits = after.bytes().take_while(u8::is_ascii_digit).count();
        rest = if digits > 0 && after.get(digits..digits + 1) == Some(">") {
            after.get(digits..).unwrap_or_default()
        } else {
            after
        };
    }
    out.push_str(rest);
    out
}

/// Whether `s` can sit between JSON quotes as is: no quote, backslash or control
/// character.
fn is_plain_json_content(s: &str) -> bool {
    !s.chars()
        .any(|c| c == '"' || c == '\\' || (c as u32) < 0x20)
}

/// The first occurrence of `needle` in `text` at or after `from` that starts a line.
fn find_at_line_start(text: &str, needle: &str, from: usize) -> Option<usize> {
    if needle.is_empty() {
        return None;
    }
    let mut at = from;
    while let Some(off) = text.get(at..).and_then(|t| t.find(needle)) {
        let pos = at + off;
        let starts_line = pos == 0 || matches!(text.as_bytes().get(pos - 1), Some(b'\n' | b'\r'));
        if starts_line {
            return Some(pos);
        }
        at = pos + 1;
        while at < text.len() && !text.is_char_boundary(at) {
            at += 1;
        }
    }
    None
}

/// The `data` field values of one event block, each with its absolute start in the
/// body. Lines end at CRLF, LF or a lone CR; a field name runs to the first colon and
/// one space after it is dropped; a leading U+FEFF at the very start of the body is not
/// part of the first line.
fn sse_data_lines(raw: &str, abs: usize) -> Vec<(usize, &str)> {
    let b = raw.as_bytes();
    let mut out = Vec::new();
    let mut i = 0;
    while i < b.len() {
        let start = i;
        while i < b.len() && b.get(i) != Some(&b'\n') && b.get(i) != Some(&b'\r') {
            i += 1;
        }
        let end = i;
        if b.get(i) == Some(&b'\r') && b.get(i + 1) == Some(&b'\n') {
            i += 2;
        } else if i < b.len() {
            i += 1;
        }
        let mut s = start;
        if abs + start == 0 && raw.get(s..).is_some_and(|t| t.starts_with('\u{feff}')) {
            s += '\u{feff}'.len_utf8();
        }
        let Some(line) = raw.get(s..end) else {
            continue;
        };
        if line.is_empty() || line.starts_with(':') {
            continue;
        }
        let (name, value_off) = match line.find(':') {
            Some(c) => {
                let v = if line.get(c + 1..c + 2) == Some(" ") {
                    c + 2
                } else {
                    c + 1
                };
                (line.get(..c).unwrap_or_default(), v)
            }
            None => (line, line.len()),
        };
        if name == "data" {
            out.push((
                abs + s + value_off,
                line.get(value_off..).unwrap_or_default(),
            ));
        }
    }
    out
}

/// The byte range of the value of the one header line named `name` in a head's text,
/// without surrounding blanks. `None` when the name occurs on no line or on more than
/// one, or when the value continues on a folded line.
fn raw_header_value(head: &str, name: &str) -> Option<(usize, usize)> {
    let mut found = None;
    let mut count = 0;
    let mut start = 0;
    let lines: Vec<(usize, &str)> = head
        .split('\n')
        .map(|l| {
            let s = start;
            start += l.len() + 1;
            (s, l.strip_suffix('\r').unwrap_or(l))
        })
        .collect();
    for (idx, (s, line)) in lines.iter().enumerate().skip(1) {
        let Some(colon) = line.find(':') else {
            continue;
        };
        if !line
            .get(..colon)
            .is_some_and(|n| n.eq_ignore_ascii_case(name))
        {
            continue;
        }
        count += 1;
        if lines
            .get(idx + 1)
            .is_some_and(|(_, next)| next.starts_with([' ', '\t']))
        {
            return None;
        }
        let value = line.get(colon + 1..).unwrap_or_default();
        let lead = value.len() - value.trim_start_matches([' ', '\t']).len();
        let trimmed = value.trim_matches([' ', '\t']);
        if trimmed.is_empty() {
            return None;
        }
        let vs = s + colon + 1 + lead;
        found = Some((vs, vs + trimmed.len()));
    }
    (count == 1).then_some(found).flatten()
}

fn head_media_type(head: &Value) -> Option<String> {
    let headers = head.get("headers")?.as_array()?;
    let value = headers.iter().find_map(|p| {
        let n = p.get(0)?.as_str()?;
        n.eq_ignore_ascii_case("content-type")
            .then(|| p.get(1).and_then(Value::as_str))
            .flatten()
    })?;
    Some(
        value
            .split(';')
            .next()
            .unwrap_or("")
            .trim()
            .to_ascii_lowercase(),
    )
}

/// The content of a normalized body, derived again from its bytes with the parsers of
/// [`crate::observe`].
fn derive_content(kind: &str, body: &[u8], ptr: &str) -> Result<Value, NormalizeError> {
    Ok(match kind {
        "json" => match serde_json::from_slice::<Value>(body) {
            Ok(v) => json!({"kind": "json", "value": v}),
            Err(_) => json!({"kind": "json-invalid"}),
        },
        "json-invalid" => json!({"kind": "json-invalid"}),
        "opaque" => json!({"kind": "opaque"}),
        "sse" => {
            let mut p = SseParser::new();
            p.feed(body, None);
            let s = p.finish();
            let events: Vec<Value> = s
                .events
                .iter()
                .map(|e| {
                    let mut m = Map::new();
                    m.insert("event".into(), opt(&e.event));
                    m.insert("id".into(), opt(&e.id));
                    m.insert("retry".into(), opt(&e.retry));
                    match e.data_json() {
                        Some(v) => m.insert("json".into(), v),
                        None => m.insert("data".into(), opt(&e.data)),
                    };
                    Value::Object(m)
                })
                .collect();
            let comments: Vec<Value> = s
                .comments
                .iter()
                .map(|c| json!({"before_event": c.before_event, "text": c.text}))
                .collect();
            json!({
                "kind": "sse",
                "events": events,
                "comments": comments,
                "unterminated": s.unterminated.as_deref().map_or(Value::Null, bytes_value),
                "bom": s.bom,
                "invalid_utf8": s.invalid_utf8,
            })
        }
        "ndjson" => {
            let mut p = NdjsonParser::new();
            p.feed(body, None);
            let s = p.finish();
            let lines: Vec<Value> = s
                .lines
                .iter()
                .map(|l| match &l.json {
                    Some(v) => json!({"json": v}),
                    None => json!({"text": l.text}),
                })
                .collect();
            json!({
                "kind": "ndjson",
                "lines": lines,
                "unterminated": s.unterminated.as_deref().map_or(Value::Null, bytes_value),
                "invalid_utf8": s.invalid_utf8,
            })
        }
        other => {
            return Err(err(
                &format!("{ptr}/kind"),
                format!("unknown content kind {other:?}"),
            ))
        }
    })
}

fn opt(v: &Option<String>) -> Value {
    v.as_ref().map_or(Value::Null, |s| Value::String(s.clone()))
}

/// Bytes as the comparison document writes them: `{"text"}` when UTF-8, else
/// `{"base64"}`.
fn bytes_value(bytes: &[u8]) -> Value {
    match std::str::from_utf8(bytes) {
        Ok(t) => json!({ "text": t }),
        Err(_) => json!({ "base64": crate::observe::base64(bytes) }),
    }
}

/// Reads a bytes object of the observation document (`{"length", "sha256", "text"}` or
/// `{..., "base64"}`): the bytes, and the text when they were UTF-8.
fn bytes_of(v: &Value, ptr: &str) -> Result<(Vec<u8>, Option<String>), NormalizeError> {
    if let Some(t) = v.get("text").and_then(Value::as_str) {
        return Ok((t.as_bytes().to_vec(), Some(t.to_string())));
    }
    if let Some(b) = v.get("base64").and_then(Value::as_str) {
        let bytes = base64_decode(b).ok_or_else(|| err(ptr, "not standard base64"))?;
        return Ok((bytes, None));
    }
    Err(err(ptr, "not a bytes object (text or base64)"))
}

/// Decodes standard base64 with padding (RFC 4648 section 4), up to
/// [`MAX_DECODED_BYTES`].
fn base64_decode(s: &str) -> Option<Vec<u8>> {
    base64_decode_within(s, MAX_DECODED_BYTES)
}

fn base64_decode_within(s: &str, max_decoded: usize) -> Option<Vec<u8>> {
    let b = s.as_bytes();
    if !b.len().is_multiple_of(4) || b.len() / 4 > max_decoded.div_ceil(3) {
        return None;
    }
    let val = |c: u8| -> Option<u32> {
        Some(match c {
            b'A'..=b'Z' => u32::from(c - b'A'),
            b'a'..=b'z' => u32::from(c - b'a') + 26,
            b'0'..=b'9' => u32::from(c - b'0') + 52,
            b'+' => 62,
            b'/' => 63,
            _ => return None,
        })
    };
    let mut out = Vec::with_capacity(b.len() / 4 * 3);
    let quads = b.len() / 4;
    for (qi, q) in b.chunks(4).enumerate() {
        let last = qi + 1 == quads;
        let pad = q.iter().rev().take_while(|&&c| c == b'=').count();
        if pad > 2 || (pad > 0 && !last) {
            return None;
        }
        let mut n = 0u32;
        for (i, &c) in q.iter().enumerate() {
            let v = if i >= 4 - pad { 0 } else { val(c)? };
            n = (n << 6) | v;
        }
        let bytes = [(n >> 16) as u8, (n >> 8) as u8, n as u8];
        out.extend_from_slice(bytes.get(..3 - pad)?);
    }
    Some(out)
}

#[cfg(test)]
mod tests;
