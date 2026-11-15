//! Owned by CNF-04 (follow-up CNF-04F). The check of a stored reference.
//!
//! A committed golden is a comparison document: the `document` of an earlier
//! [`Normalizer::normalize`] of the reference side, read back. It is replayed with
//! [`Normalized::stored`](super::Normalized::stored) and compared with
//! [`crate::compare::compare`]; it is never passed to the normalizer again. So that a
//! stored document cannot carry a raw volatile value into a comparison, it must be a fixed
//! point of normalization under the context its run was recorded with: running the
//! normalizer's own passes over it again changes nothing. The first value that would
//! still be replaced is refused, with its pointer.
//!
//! What is checked, against the same list entries and class checks as
//! [`Normalizer::normalize`]:
//!
//! - the document has exactly the members a comparison document has, in the shape the
//!   normalizer writes them: UTF-8 bytes as text, never as base64; each content kind the
//!   one the client gives a body with that head; no wire byte count in a disconnect;
//! - no header value, in the header list or in the raw head, still passes the class check
//!   of a listed header (a `Date` in IMF-fixdate form inside the run window, a non-empty
//!   `Server` value), unless it is the placeholder itself;
//! - no body, stream event, NDJSON line, Prometheus sample, file, file path or log line
//!   still holds a value that a list entry or a decided rename would replace;
//! - the derived members (the content beside each body, the parsed JSON beside each
//!   file) are what the normalizer derives from the text beside them.
//!
//! One member may hold raw values and still be a fixed point: the wire of an exchange the
//! normalizer found inconsistent (chunked framing, or bytes past the body that the
//! client's timing did not explain). The normalizer keeps those bytes as received, raw
//! `Date` and `Server` values included, and the comparator compares them exactly, so a
//! raw value there can only make a difference, never hide one.

use serde_json::{Map, Value};

use std::collections::BTreeMap;

use super::{
    bytes_of, classes, derive_content, err, head_media_type, json_text, raw_header_value, Loc,
    NormalizeError, Normalizer, Run, Side, SideContext, MAX_TEXT_BYTES,
};

/// The members of a comparison document, in the order the normalizer writes them.
const DOCUMENT_MEMBERS: &[&str] = &["http", "engine_tape", "files", "log", "exit"];

/// The members of one exchange of a comparison document.
const EXCHANGE_MEMBERS: &[&str] = &[
    "request_complete",
    "write_error",
    "interim",
    "head",
    "framing",
    "body",
    "content",
    "end",
    "server_closed",
    "disconnect",
    "wire",
];

/// The members of one head of a comparison document.
const HEAD_MEMBERS: &[&str] = &["version", "code", "reason", "headers", "raw"];

/// The members of one file of a comparison document.
const FILE_MEMBERS: &[&str] = &["path", "bytes", "is_json", "json"];

/// The members of an object, refused unless they are exactly `want`, in that order.
fn members<'v>(
    v: &'v Value,
    want: &[&str],
    ptr: &str,
) -> Result<&'v Map<String, Value>, NormalizeError> {
    let o = v
        .as_object()
        .ok_or_else(|| err(ptr, "not an object of a comparison document"))?;
    let keys: Vec<&str> = o.keys().map(String::as_str).collect();
    if keys != want {
        return Err(err(
            ptr,
            format!("not a comparison document: members {keys:?}, expected {want:?}"),
        ));
    }
    Ok(o)
}

fn member<'v>(o: &'v Map<String, Value>, k: &str, ptr: &str) -> Result<&'v Value, NormalizeError> {
    o.get(k)
        .ok_or_else(|| err(&format!("{ptr}/{k}"), "missing"))
}

/// A text member (`{"text"}` or `{"base64"}`, one member only). The normalizer writes
/// UTF-8 bytes as `{"text"}` and only other bytes as `{"base64"}` (`bytes_value`), so a
/// `{"base64"}` member whose bytes are UTF-8 is refused: it would keep its text from
/// every check below.
fn text_of(v: &Value, ptr: &str) -> Result<(Vec<u8>, Option<String>), NormalizeError> {
    let one = v
        .as_object()
        .is_some_and(|o| o.len() == 1 && (o.contains_key("text") || o.contains_key("base64")));
    if !one {
        return Err(err(ptr, "not a text of a comparison document"));
    }
    let (bytes, text) = bytes_of(v, ptr)?;
    if text.is_none() && std::str::from_utf8(&bytes).is_ok() {
        return Err(err(
            &format!("{ptr}/base64"),
            "the normalizer writes UTF-8 bytes as text: not a fixed point",
        ));
    }
    Ok((bytes, text))
}

/// The content kind the client gives a body with this head (`client::read`, which picks
/// the parser by the media type of the first `Content-Type` header): a stored kind must
/// be one of these, so that relabelling it cannot choose which checks run.
fn kinds_for(head: &Value) -> &'static [&'static str] {
    if head.is_null() {
        return &["opaque"];
    }
    match head_media_type(head).as_deref() {
        Some("text/event-stream") => &["sse"],
        Some("application/x-ndjson") => &["ndjson"],
        Some("application/json") => &["json", "json-invalid"],
        _ => &["opaque"],
    }
}

impl Normalizer {
    /// Checks that `document` is a stored reference: a comparison document of the
    /// reference side that is a fixed point of this normalizer under `ctx`, the context
    /// its run was recorded with. Fails with the pointer of the first value that is not.
    pub fn check_stored(&self, document: &Value, ctx: &SideContext) -> Result<(), NormalizeError> {
        let mut run = Run {
            n: self,
            side: Side::Reference,
            ctx,
            ids: BTreeMap::new(),
            applied: Vec::new(),
            applied_truncated: false,
            issues: Vec::new(),
        };
        run.stored_document(document)
    }
}

impl Run<'_> {
    /// Fails when a pass recorded a replacement since `mark`.
    fn unchanged(&self, mark: usize, ptr: &str) -> Result<(), NormalizeError> {
        match self.applied.get(mark) {
            None if !self.applied_truncated => Ok(()),
            None => Err(err(ptr, "a value here would still be replaced")),
            Some(a) => Err(err(
                &a.pointer,
                format!(
                    "a stored reference holds a value that normalization still replaces ({}): it is not a fixed point",
                    a.source
                ),
            )),
        }
    }

    fn stored_document(&mut self, v: &Value) -> Result<(), NormalizeError> {
        let o = members(v, DOCUMENT_MEMBERS, "")?;
        let http = member(o, "http", "")?
            .as_array()
            .ok_or_else(|| err("/http", "not an array"))?;
        for (i, ex) in http.iter().enumerate() {
            self.stored_exchange(ex, &format!("/http/{i}"))?;
        }
        let files = member(o, "files", "")?
            .as_array()
            .ok_or_else(|| err("/files", "not an array"))?;
        for (i, f) in files.iter().enumerate() {
            self.stored_file(f, &format!("/files/{i}"))?;
        }
        let log = member(o, "log", "")?
            .as_array()
            .ok_or_else(|| err("/log", "not an array"))?;
        for (i, l) in log.iter().enumerate() {
            let ptr = format!("/log/{i}");
            let s = l.as_str().ok_or_else(|| err(&ptr, "not a string"))?;
            let mark = self.applied.len();
            let out = self.log_line(s, &ptr);
            self.unchanged(mark, &ptr)?;
            if out != s {
                return Err(err(&ptr, "a log line normalization still changes"));
            }
        }
        Ok(())
    }

    fn stored_exchange(&mut self, ex: &Value, ptr: &str) -> Result<(), NormalizeError> {
        let o = members(ex, EXCHANGE_MEMBERS, ptr)?;
        let interim = member(o, "interim", ptr)?
            .as_array()
            .ok_or_else(|| err(&format!("{ptr}/interim"), "not an array"))?;
        for (i, h) in interim.iter().enumerate() {
            self.stored_head(h, &format!("{ptr}/interim/{i}"))?;
        }
        let head = member(o, "head", ptr)?;
        if !head.is_null() {
            self.stored_head(head, &format!("{ptr}/head"))?;
        }
        let bp = format!("{ptr}/body");
        let (body, text) = text_of(member(o, "body", ptr)?, &bp)?;
        let content = member(o, "content", ptr)?;
        let kind = content
            .get("kind")
            .and_then(Value::as_str)
            .ok_or_else(|| err(&format!("{ptr}/content/kind"), "missing"))?
            .to_string();
        if !kinds_for(head).contains(&kind.as_str()) {
            return Err(err(
                &format!("{ptr}/content/kind"),
                format!(
                    "the content kind {kind:?} is not the one the head gives the body ({:?}): not a comparison document",
                    kinds_for(head)
                ),
            ));
        }
        if kind == "json-invalid" && serde_json::from_slice::<Value>(&body).is_ok() {
            return Err(err(
                &format!("{ptr}/content/kind"),
                "a body that parses as JSON is not json-invalid: not a comparison document",
            ));
        }
        if let Some(d) = member(o, "disconnect", ptr)?.as_object() {
            if d.contains_key("wire_bytes") {
                return Err(err(
                    &format!("{ptr}/disconnect/wire_bytes"),
                    "the normalizer removes the wire byte count of a disconnect: not a fixed point",
                ));
            }
        }
        // the wire is "consistent", or the bytes received as the normalizer keeps them for
        // an exchange it finds inconsistent (chunked framing, bytes past the body): those
        // are compared exactly, so a raw value in them can only be a difference
        let wire = member(o, "wire", ptr)?;
        if wire.as_str() != Some("consistent") {
            text_of(wire, &format!("{ptr}/wire"))?;
        }
        if let Some(t) = text.as_deref().filter(|t| t.len() <= MAX_TEXT_BYTES) {
            let mark = self.applied.len();
            let edits = match kind.as_str() {
                "json" => self.json_edits(t, &bp),
                "sse" => self.sse_edits(t, &body, &bp),
                "ndjson" => self.ndjson_edits(t, &bp),
                "opaque" if head_media_type(head).as_deref() == Some("text/plain") => {
                    self.metric_edits(t, &bp)
                }
                _ => Vec::new(),
            };
            self.unchanged(mark, &bp)?;
            if !edits.is_empty() {
                return Err(err(&bp, "a body normalization still changes"));
            }
        }
        let derived = derive_content(&kind, &body, &format!("{ptr}/content"))?;
        if &derived != content {
            return Err(err(
                &format!("{ptr}/content"),
                "the content is not the one derived from the body beside it",
            ));
        }
        Ok(())
    }

    /// A head: no listed header value, in the list or in the raw text, still passes its
    /// class check.
    fn stored_head(&mut self, h: &Value, ptr: &str) -> Result<(), NormalizeError> {
        let o = members(h, HEAD_MEMBERS, ptr)?;
        let headers = member(o, "headers", ptr)?
            .as_array()
            .ok_or_else(|| err(&format!("{ptr}/headers"), "not an array"))?;
        let mut pairs: Vec<(&str, &str)> = Vec::new();
        for (i, pair) in headers.iter().enumerate() {
            let hp = format!("{ptr}/headers/{i}");
            match pair.as_array().map(Vec::as_slice) {
                Some([Value::String(n), Value::String(v)]) => pairs.push((n, v)),
                _ => return Err(err(&hp, "not a [name, value] pair")),
            }
        }
        let rp = format!("{ptr}/raw");
        let (_, raw_text) = text_of(member(o, "raw", ptr)?, &rp)?;
        let n: &Normalizer = self.n;
        for f in &n.fields {
            let Loc::Header(name) = &f.loc else { continue };
            let at: Vec<usize> = pairs
                .iter()
                .enumerate()
                .filter(|(_, (n, _))| n.eq_ignore_ascii_case(name))
                .map(|(i, _)| i)
                .collect();
            // the normalizer replaces a listed header, in the list and in the raw head,
            // only when it is present once; a repeated one stays as sent in both
            let [i] = at.as_slice() else { continue };
            if let Some((_, value)) = pairs.get(*i) {
                if self.raw_header(name, value) {
                    return Err(err(
                        &format!("{ptr}/headers/{i}/1"),
                        format!(
                            "a stored reference holds a raw value of {} (volatile:{}): it is not a fixed point",
                            name, f.id
                        ),
                    ));
                }
            }
            if let Some(t) = &raw_text {
                if let Some(value) = raw_header_value(t, name).and_then(|(s, e)| t.get(s..e)) {
                    if self.raw_header(name, value) {
                        return Err(err(
                            &format!("{rp}/text"),
                            format!(
                                "a stored reference holds a raw value of {} in its raw head (volatile:{}): it is not a fixed point",
                                name, f.id
                            ),
                        ));
                    }
                }
            }
        }
        Ok(())
    }

    /// Whether a header value of a listed header would be replaced: it is not the
    /// placeholder and it passes the class check.
    fn raw_header(&self, name: &str, value: &str) -> bool {
        if value.is_empty() || value == "<header>" {
            return false;
        }
        if name.eq_ignore_ascii_case("date") {
            let w = self.ctx.window;
            return classes::imf_fixdate(value).is_some_and(|t| w.contains(t, 0.0));
        }
        true
    }

    fn stored_file(&mut self, f: &Value, ptr: &str) -> Result<(), NormalizeError> {
        let o = members(f, FILE_MEMBERS, ptr)?;
        let path = member(o, "path", ptr)?
            .as_str()
            .ok_or_else(|| err(&format!("{ptr}/path"), "not a string"))?;
        let mark = self.applied.len();
        let (renamed, sources) = self.rename_path(path);
        if !sources.is_empty() || renamed != path {
            return Err(err(
                &format!("{ptr}/path"),
                format!(
                    "a stored reference holds a file name a decided rename still changes ({sources:?}): it is not a fixed point"
                ),
            ));
        }
        let new_path = self.path_volatile(path, ptr);
        self.unchanged(mark, &format!("{ptr}/path"))?;
        if new_path != path {
            return Err(err(
                &format!("{ptr}/path"),
                "a file path normalization still changes",
            ));
        }
        let bp = format!("{ptr}/bytes");
        let (bytes, text) = text_of(member(o, "bytes", ptr)?, &bp)?;
        if let Some(t) = text.as_deref().filter(|t| t.len() <= MAX_TEXT_BYTES) {
            let mark = self.applied.len();
            let edits = if json_text::scan(t).is_some() {
                self.json_edits(t, &bp)
            } else {
                self.ndjson_edits(t, &bp)
            };
            self.unchanged(mark, &bp)?;
            if !edits.is_empty() {
                return Err(err(&bp, "a file normalization still changes"));
            }
        }
        let parsed: Option<Value> = serde_json::from_slice(&bytes).ok();
        if member(o, "is_json", ptr)? != &Value::Bool(parsed.is_some())
            || member(o, "json", ptr)? != parsed.as_ref().unwrap_or(&Value::Null)
        {
            return Err(err(
                &format!("{ptr}/json"),
                "the parsed JSON is not the one derived from the bytes beside it",
            ));
        }
        Ok(())
    }
}
