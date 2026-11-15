//! CNF-04 follow-up: the comparator's open points, each pinned by negative tests that
//! fail if its rule were widened.
//!
//! - The `Content-Length` value is a derived value (lead decision LD44): it is rewritten
//!   as the length of the normalized body only when the read was complete, the framing is
//!   Content-Length and the header is exactly the number of body bytes received; in every
//!   other case it is compared as sent, and its name and position stay observable.
//! - A stored reference (`Normalized::stored`) is refused unless it is a fixed point of
//!   normalization, with the pointer of the offending value.
//! - An annotation names the kind of difference it covers, or carries both expected
//!   values; an exact pointer alone suppresses nothing.
//! - The status figures and the done stamp of a resumable answer are volatile at the top
//!   level of a document only.
//!
//! No donor test method is re-expressed here: CNF-04 owns none. The shapes follow
//! project-maya serve/server.py:5457-5463 (`_json`), 6087-6099 (GET /status), 3334-3344
//! (the live block of GET /metrics) and 5086-5095 (the last line of an answer's file) at
//! 7e68a30f.

use std::path::PathBuf;

use console_conformance::compare::{
    compare, compare_documents, Annotation, AnnotationProblem, ApprovedIds, CoveredKind, DiffKind,
    Report,
};
use console_conformance::normalize::{Normalized, Normalizer, RunWindow, Side, SideContext};
use console_conformance::observe::{
    Content, End, Exchange, ExitRecord, FileRecord, Framing, Header, Observation, ResponseHead,
};
use console_conformance::scenario::{load_rename_map, load_volatile_fields, VolatileFields};
use serde_json::{json, Value};

// ------------------------------------------------------------------ fixture

fn contracts() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../specs/022-console-serving-parity/contracts")
}

fn volatile() -> VolatileFields {
    load_volatile_fields(&contracts().join("volatile-fields.json"))
        .unwrap_or_else(|e| panic!("volatile-fields.json: {e}"))
}

fn normalizer_with(list: &VolatileFields) -> Normalizer {
    let renames = load_rename_map(&contracts().join("rename-map.json"))
        .unwrap_or_else(|e| panic!("rename-map.json: {e}"));
    Normalizer::new(list, renames).unwrap_or_else(|e| panic!("normalizer: {e}"))
}

fn normalizer() -> Normalizer {
    normalizer_with(&volatile())
}

fn approved() -> ApprovedIds {
    let text = std::fs::read_to_string(contracts().join("deviations.md"))
        .unwrap_or_else(|e| panic!("deviations.md: {e}"));
    ApprovedIds::from_register(&text).unwrap_or_else(|e| panic!("{e}"))
}

/// The run-dependent values of one side.
struct Run {
    t: u64,
    port: u16,
    server: &'static str,
    date: &'static str,
    id: &'static str,
    /// The elapsed time, the rate and the mean rate: of other widths on each side.
    figs: [&'static str; 3],
    prefix: &'static str,
}

const REF: Run = Run {
    t: 1_731_600_000,
    port: 41_001,
    server: "BaseHTTP/0.6 Python/3.14.7",
    date: "Thu, 14 Nov 2024 16:00:00 GMT",
    id: "0123456789abcdef01234567",
    figs: ["12.25", "1234.5", "10.25"],
    prefix: "[maya] ",
};

const CAND: Run = Run {
    t: 1_800_000_000,
    port: 52_123,
    server: "pulsar-console/0.1.0",
    date: "Fri, 15 Jan 2027 08:00:00 GMT",
    id: "fedcba9876543210fedcba98",
    figs: ["3.5", "7.5", "6.5"],
    prefix: "[console] ",
};

fn ctx(r: &Run) -> SideContext {
    SideContext::new(RunWindow {
        start: r.t as f64,
        end: r.t as f64 + 60.0,
    })
    .with_port(r.port)
}

/// One side's observation, before it is recorded.
struct Parts {
    headers: Vec<(String, String)>,
    body: String,
    framing: Framing,
    end: End,
    files: Vec<(String, String)>,
    log: Vec<String>,
}

/// GET /status while an answer is written (serve/server.py:6087-6099): the figures at
/// the top level, with `extra` members after them.
fn status_body(r: &Run, extra: &str) -> String {
    format!(
        "{{\"busy\": true, \"elapsed_s\": {}, \"tokens_per_s\": {}, \"tokens_per_s_mean\": {}{extra}}}",
        r.figs[0], r.figs[1], r.figs[2]
    )
}

fn parts(r: &Run) -> Parts {
    let body = status_body(r, "");
    let cid = format!("chatcmpl-{}", r.id);
    Parts {
        headers: vec![
            ("Server".into(), r.server.into()),
            ("Date".into(), r.date.into()),
            ("Content-Type".into(), "application/json".into()),
            ("Content-Length".into(), body.len().to_string()),
        ],
        framing: Framing::ContentLength(body.len() as u64),
        body,
        end: End::Complete,
        files: vec![(
            format!("answers/{cid}.jsonl"),
            format!(
                "{{\"id\": \"{cid}\", \"created\": {}}}\n{{\"_done\": {}.25}}\n",
                r.t + 2,
                r.t + 8
            ),
        )],
        log: vec![
            format!("ready: http://127.0.0.1:{}/v1", r.port),
            format!("{}listening", r.prefix),
        ],
    }
}

/// Replaces the body, keeping the Content-Length header and the framing exact.
fn set_body(p: &mut Parts, body: String) {
    for (n, v) in &mut p.headers {
        if n == "Content-Length" {
            *v = body.len().to_string();
        }
    }
    p.framing = Framing::ContentLength(body.len() as u64);
    p.body = body;
}

fn build(p: &Parts) -> Value {
    let mut raw = b"HTTP/1.0 200 OK\r\n".to_vec();
    for (n, v) in &p.headers {
        raw.extend_from_slice(format!("{n}: {v}\r\n").as_bytes());
    }
    raw.extend_from_slice(b"\r\n");
    let body = p.body.clone().into_bytes();
    let mut wire = raw.clone();
    wire.extend_from_slice(&body);
    let content = match serde_json::from_slice(&body) {
        Ok(v) => Content::Json(v),
        Err(e) => Content::InvalidJson(e.to_string()),
    };
    let request = b"GET /status HTTP/1.0\r\n\r\n".to_vec();
    Observation {
        http: vec![Exchange {
            request_sent: request.len() as u64,
            request,
            write_error: None,
            interim: Vec::new(),
            head: Some(ResponseHead {
                version: "HTTP/1.0".into(),
                code: 200,
                reason: "OK".into(),
                headers: p
                    .headers
                    .iter()
                    .map(|(n, v)| Header {
                        name: n.clone(),
                        value: v.clone(),
                    })
                    .collect(),
                raw,
            }),
            framing: Some(p.framing.clone()),
            body,
            content,
            end: p.end.clone(),
            server_closed: Some(true),
            disconnect: None,
            wire,
        }],
        engine_tape: Some(json!([])),
        files: p
            .files
            .iter()
            .map(|(path, b)| FileRecord::from_bytes(path, b.clone().into_bytes()))
            .collect(),
        log: p.log.clone(),
        exit: Some(ExitRecord {
            code: Some(0),
            signal: None,
        }),
    }
    .to_json()
}

fn check_with(n: &Normalizer, a: &Parts, b: &Parts, annotations: &[Annotation]) -> Report {
    compare_documents(
        n,
        &build(a),
        &ctx(&REF),
        &build(b),
        &ctx(&CAND),
        annotations,
        &approved(),
    )
    .unwrap_or_else(|e| panic!("normalize: {e}"))
}

fn check(a: &Parts, b: &Parts) -> Report {
    check_with(&normalizer(), a, b, &[])
}

fn pointers(r: &Report) -> Vec<String> {
    r.differences.iter().map(|d| d.pointer.clone()).collect()
}

fn expect_diff(r: &Report, pointer: &str) {
    assert!(
        !r.passed() && pointers(r).iter().any(|p| p == pointer),
        "no difference at {pointer}; got {}",
        serde_json::to_string_pretty(&r.to_json()).unwrap_or_default()
    );
}

fn expect_clean(r: &Report) {
    assert!(
        r.clean(),
        "{}",
        serde_json::to_string_pretty(&r.to_json()).unwrap_or_default()
    );
}

const CL_VALUE: &str = "/http/0/head/headers/3/1";

/// The normalized Content-Length value of one side, and whether the entry applied.
fn derived(p: &Parts, r: &Run, side: Side) -> (Value, bool) {
    let out = normalizer()
        .normalize(&build(p), side, &ctx(r))
        .unwrap_or_else(|e| panic!("{e}"));
    let applied = out
        .applied
        .iter()
        .any(|a| a.source == "volatile:header-content-length");
    (
        out.document["http"][0]["head"]["headers"][3][1].clone(),
        applied,
    )
}

// ------------------------------------------------------------------ Content-Length (LD44)

#[test]
fn a_content_length_that_describes_the_body_is_the_normalized_length() {
    // the figures have other widths, so the raw lengths differ; the normalized bodies
    // agree, and so do the derived lengths
    let (a, b) = (parts(&REF), parts(&CAND));
    assert_ne!(a.body.len(), b.body.len());
    expect_clean(&check(&a, &b));
    for (p, r, side) in [(&a, &REF, Side::Reference), (&b, &CAND, Side::Candidate)] {
        let out = normalizer()
            .normalize(&build(p), side, &ctx(r))
            .unwrap_or_else(|e| panic!("{e}"));
        let body = out.document["http"][0]["body"]["text"]
            .as_str()
            .unwrap_or_default()
            .to_string();
        assert_eq!(
            out.document["http"][0]["head"]["headers"][3],
            json!(["Content-Length", body.len().to_string()])
        );
        assert_eq!(
            out.document["http"][0]["framing"]["length"],
            json!(body.len())
        );
        let raw = out.document["http"][0]["head"]["raw"]["text"]
            .as_str()
            .unwrap_or_default();
        assert!(raw.contains(&format!("Content-Length: {}\r\n", body.len())));
        assert!(out
            .applied
            .iter()
            .any(|x| x.source == "volatile:header-content-length"));
    }
}

#[test]
fn a_body_that_differs_after_normalization_differs_in_its_length_too() {
    let a = parts(&REF);
    let mut b = parts(&CAND);
    let body = status_body(&CAND, ", \"phase\": \"x\"");
    set_body(&mut b, body);
    let r = check(&a, &b);
    expect_diff(&r, CL_VALUE);
    expect_diff(&r, "/http/0/framing/length");
    expect_diff(&r, "/http/0/body/text");
}

#[test]
fn a_content_length_is_compared_as_sent_unless_it_describes_a_complete_body() {
    // each case is applied to both sides; were the value derived anyway, the two
    // sides would agree, so each case requires the raw values on both sides and the
    // difference between them
    type Case = (&'static str, fn(&mut Parts));
    let cases: [Case; 6] = [
        ("the read ended early", |p| p.end = End::Truncated),
        ("the client disconnected", |p| p.end = End::Disconnected),
        ("the body is close-delimited", |p| {
            p.framing = Framing::CloseDelimited
        }),
        ("the header is one more than the body", |p| {
            let n = p.body.len() + 1;
            p.headers[3].1 = n.to_string();
            p.framing = Framing::ContentLength(n as u64);
        }),
        ("the header has a leading zero", |p| {
            p.headers[3].1 = format!("0{}", p.body.len());
        }),
        ("the header is repeated", |p| {
            let v = p.headers[3].1.clone();
            p.headers.push(("Content-Length".into(), v));
        }),
    ];
    for (what, mutate) in cases {
        let (mut a, mut b) = (parts(&REF), parts(&CAND));
        mutate(&mut a);
        mutate(&mut b);
        for (p, r, side) in [(&a, &REF, Side::Reference), (&b, &CAND, Side::Candidate)] {
            let (value, applied) = derived(p, r, side);
            assert!(!applied, "{what}: the value was derived");
            assert_eq!(value, json!(p.headers[3].1), "{what}");
        }
        let r = check(&a, &b);
        expect_diff(&r, CL_VALUE);
    }
}

#[test]
fn the_content_length_name_and_position_stay_observable() {
    let a = parts(&REF);
    let mut b = parts(&CAND);
    b.headers[3].0 = "content-length".into();
    expect_diff(&check(&a, &b), "/http/0/head/headers/3/0");
    let mut b = parts(&CAND);
    b.headers.swap(2, 3);
    let r = check(&a, &b);
    expect_diff(&r, "/http/0/head/headers/2/0");
    expect_diff(&r, "/http/0/head/headers/3/0");
    let mut b = parts(&CAND);
    b.headers.remove(3);
    expect_diff(&check(&a, &b), "/http/0/head/headers/3");
}

// ------------------------------------------------------------------ stored references

fn stored_reference() -> Value {
    let out = normalizer()
        .normalize(&build(&parts(&REF)), Side::Reference, &ctx(&REF))
        .unwrap_or_else(|e| panic!("{e}"));
    let text = serde_json::to_string(&out.document).unwrap_or_default();
    serde_json::from_str(&text).unwrap_or_else(|e| panic!("{e}"))
}

fn stored(v: Value) -> Result<Normalized, String> {
    Normalized::stored(v, &normalizer(), &ctx(&REF)).map_err(|e| e.pointer)
}

/// Replaces `from` by `to` in the string at `pointer`, once.
fn edit(v: &mut Value, pointer: &str, from: &str, to: &str) {
    let slot = v
        .pointer_mut(pointer)
        .unwrap_or_else(|| panic!("no {pointer}"));
    let s = slot.as_str().unwrap_or_default().to_string();
    assert!(s.contains(from), "{pointer} has no {from:?}: {s}");
    *slot = Value::String(s.replacen(from, to, 1));
}

#[test]
fn a_stored_reference_that_is_a_fixed_point_replays() {
    let doc = stored_reference();
    let n = normalizer();
    let fresh = n
        .normalize(&build(&parts(&CAND)), Side::Candidate, &ctx(&CAND))
        .unwrap_or_else(|e| panic!("{e}"));
    let s = stored(doc).unwrap_or_else(|p| panic!("refused at {p}"));
    expect_clean(&compare(&s, &fresh, &[], &approved(), Some(n.renames())));
}

#[test]
fn a_raw_observation_is_not_a_stored_reference() {
    // an observation has the same top-level members; its exchanges are not those of a
    // comparison document
    assert_eq!(
        stored(build(&parts(&REF))).err().as_deref(),
        Some("/http/0")
    );
    assert!(stored(json!({})).is_err());
    assert!(stored(json!([])).is_err());
    let mut doc = stored_reference();
    doc["extra"] = json!(1);
    assert_eq!(stored(doc).err().as_deref(), Some(""));
    let mut doc = stored_reference();
    doc["http"][0]["request"] = json!({"text": "GET / HTTP/1.0\r\n\r\n"});
    assert_eq!(stored(doc).err().as_deref(), Some("/http/0"));
}

#[test]
fn a_raw_volatile_value_in_a_stored_reference_is_refused_with_its_pointer() {
    let date = REF.date;
    let port = REF.port.to_string();
    let raw_id = format!("chatcmpl-{}", REF.id);
    // (where to edit, what to put back, the pointer the refusal must name)
    let cases: Vec<(&str, String, String, &str)> = vec![
        (
            "/http/0/head/headers/0/1",
            "<header>".into(),
            REF.server.into(),
            "/http/0/head/headers/0/1",
        ),
        (
            "/http/0/head/headers/1/1",
            "<header>".into(),
            date.into(),
            "/http/0/head/headers/1/1",
        ),
        (
            "/http/0/head/raw/text",
            "Date: <header>".into(),
            format!("Date: {date}"),
            "/http/0/head/raw/text",
        ),
        (
            "/http/0/body/text",
            "\"<num:f>\"".into(),
            REF.figs[0].into(),
            "/http/0/body#/elapsed_s",
        ),
        ("/log/0", "{{port}}".into(), port, "/log/0"),
        ("/log/1", CAND.prefix.into(), REF.prefix.into(), "/log/1"),
        (
            "/files/0/path",
            "<chatcmpl-#1>".into(),
            raw_id,
            "/files/0/path",
        ),
    ];
    for (at, from, to, want) in cases {
        let mut doc = stored_reference();
        edit(&mut doc, at, &from, &to);
        assert_eq!(stored(doc).err().as_deref(), Some(want), "{at}: {to}");
    }
    // a raw stamp in a file line, with the parsed JSON beside it kept consistent: the
    // text is checked first
    let mut doc = stored_reference();
    edit(
        &mut doc,
        "/files/0/bytes/text",
        "\"<epoch-s:f>\"",
        "1731600008.25",
    );
    let err = stored(doc).err().unwrap_or_default();
    assert!(err.starts_with("/files/0/bytes"), "{err}");
}

#[test]
fn derived_members_of_a_stored_reference_must_match_their_text() {
    let mut doc = stored_reference();
    doc["http"][0]["content"]["value"]["busy"] = json!(false);
    assert_eq!(stored(doc).err().as_deref(), Some("/http/0/content"));
    let mut doc = stored_reference();
    doc["files"][0]["is_json"] = json!(true);
    assert_eq!(stored(doc).err().as_deref(), Some("/files/0/json"));
}

#[test]
fn a_value_that_fails_its_class_check_may_stay_in_a_stored_reference() {
    // the normalizer keeps a Date outside the run window as sent, so a stored document
    // that holds one is still a fixed point (and the value is compared exactly)
    let mut doc = stored_reference();
    edit(
        &mut doc,
        "/http/0/head/headers/1/1",
        "<header>",
        "Thu, 14 Nov 2024 23:00:00 GMT",
    );
    assert!(stored(doc).is_ok());
}

#[test]
fn a_base64_body_or_head_cannot_hide_a_raw_value() {
    use console_conformance::observe::base64;
    // the body with a raw figure put back, written as base64, its content kept consistent
    let mut doc = stored_reference();
    let t = doc["http"][0]["body"]["text"]
        .as_str()
        .unwrap_or_default()
        .to_string();
    let raw = t.replacen("\"<num:f>\"", REF.figs[0], 1);
    assert_ne!(raw, t);
    doc["http"][0]["body"] = json!({"base64": base64(raw.as_bytes())});
    doc["http"][0]["content"]["value"] =
        serde_json::from_str(&raw).unwrap_or_else(|e| panic!("{e}"));
    assert_eq!(stored(doc).err().as_deref(), Some("/http/0/body/base64"));
    // the raw head with a Date inside the window, written as base64
    let mut doc = stored_reference();
    let t = doc["http"][0]["head"]["raw"]["text"]
        .as_str()
        .unwrap_or_default()
        .to_string();
    let raw = t.replacen("Date: <header>", &format!("Date: {}", REF.date), 1);
    assert_ne!(raw, t);
    doc["http"][0]["head"]["raw"] = json!({"base64": base64(raw.as_bytes())});
    assert_eq!(
        stored(doc).err().as_deref(),
        Some("/http/0/head/raw/base64")
    );
    // a file's bytes, and a wire, the same way
    let mut doc = stored_reference();
    let t = doc["files"][0]["bytes"]["text"]
        .as_str()
        .unwrap_or_default()
        .to_string();
    doc["files"][0]["bytes"] = json!({"base64": base64(t.as_bytes())});
    assert_eq!(stored(doc).err().as_deref(), Some("/files/0/bytes/base64"));
    let mut doc = stored_reference();
    doc["http"][0]["wire"] = json!({"base64": base64(b"HTTP/1.0 200 OK\r\n\r\n")});
    assert_eq!(stored(doc).err().as_deref(), Some("/http/0/wire/base64"));
    // bytes that are not UTF-8 are written as base64, and accepted there
    let mut doc = stored_reference();
    doc["http"][0]["wire"] = json!({"base64": base64(&[0xff, 0xfe, 0x00])});
    assert!(stored(doc).is_ok());
}

#[test]
fn a_relabelled_content_kind_cannot_hide_a_raw_value() {
    // the head says application/json: the kind is json (or json-invalid), never another
    // one that would choose other checks
    for kind in ["opaque", "ndjson", "sse"] {
        let mut doc = stored_reference();
        edit(&mut doc, "/http/0/body/text", "\"<num:f>\"", REF.figs[0]);
        doc["http"][0]["content"] = json!({"kind": kind});
        assert_eq!(
            stored(doc).err().as_deref(),
            Some("/http/0/content/kind"),
            "{kind}"
        );
    }
    // a body that parses is not json-invalid
    let mut doc = stored_reference();
    edit(&mut doc, "/http/0/body/text", "\"<num:f>\"", REF.figs[0]);
    doc["http"][0]["content"] = json!({"kind": "json-invalid"});
    assert_eq!(stored(doc).err().as_deref(), Some("/http/0/content/kind"));
    // a head of another media type gives another kind: the relabel is caught there too
    let mut doc = stored_reference();
    edit(
        &mut doc,
        "/http/0/head/headers/2/1",
        "application/json",
        "application/x-ndjson",
    );
    assert_eq!(stored(doc).err().as_deref(), Some("/http/0/content/kind"));
}

#[test]
fn the_disconnect_and_the_wire_of_a_stored_reference_are_checked() {
    // the normalizer removes the wire byte count of a disconnect
    let mut doc = stored_reference();
    doc["http"][0]["disconnect"] =
        json!({"trigger": "after-bytes", "n": 1, "mode": "close", "fired": true, "wire_bytes": 10});
    assert_eq!(
        stored(doc).err().as_deref(),
        Some("/http/0/disconnect/wire_bytes")
    );
    let mut doc = stored_reference();
    doc["http"][0]["disconnect"] =
        json!({"trigger": "after-bytes", "n": 1, "mode": "close", "fired": true});
    assert!(stored(doc).is_ok());
    // a wire is "consistent" or a text member
    for bad in [
        json!("inconsistent"),
        json!(1),
        json!({"text": "a", "x": 1}),
    ] {
        let mut doc = stored_reference();
        doc["http"][0]["wire"] = bad.clone();
        assert_eq!(stored(doc).err().as_deref(), Some("/http/0/wire"), "{bad}");
    }
    // the bytes received of an exchange the normalizer found inconsistent stay as
    // received (stored.rs module doc): they are compared exactly
    let mut doc = stored_reference();
    doc["http"][0]["wire"] = json!({"text": format!(
        "HTTP/1.0 200 OK\r\nServer: {}\r\nDate: {}\r\n\r\n",
        REF.server, REF.date
    )});
    assert!(stored(doc).is_ok());
}

#[test]
fn a_repeated_listed_header_stays_as_sent_in_a_stored_reference() {
    // the normalizer replaces a listed header only when it is present once, so a
    // repeated Date or Server stays as sent, in the list and in the raw head, and the
    // normalized document still replays
    for name in ["Date", "Server"] {
        let mut p = parts(&REF);
        let v = p
            .headers
            .iter()
            .find(|(n, _)| n == name)
            .map(|(_, v)| v.clone())
            .unwrap_or_default();
        p.headers.push((name.into(), v.clone()));
        let out = normalizer()
            .normalize(&build(&p), Side::Reference, &ctx(&REF))
            .unwrap_or_else(|e| panic!("{e}"));
        let raw = out.document["http"][0]["head"]["raw"]["text"]
            .as_str()
            .unwrap_or_default();
        assert!(raw.contains(&format!("{name}: {v}\r\n")), "{name}: {raw}");
        stored(out.document).unwrap_or_else(|p| panic!("{name}: refused at {p}"));
    }
}

// ------------------------------------------------------------------ annotations

#[test]
fn an_annotation_must_say_what_it_covers() {
    let a = parts(&REF);
    let mut b = parts(&CAND);
    b.headers[2].1 = "text/json".into();
    let at = "/http/0/head/headers/2/1";
    // an exact pointer alone, or one expected value without a kind: refused
    for bare in [
        Annotation::new("SEC-1.3", at),
        Annotation::new("SEC-1.3", at).expecting(Some(json!("application/json")), None),
        Annotation::new("SEC-1.3", at).expecting(None, Some(json!("text/json"))),
    ] {
        let r = check_with(&normalizer(), &a, &b, &[bare]);
        expect_diff(&r, at);
        assert!(r.suppressed.is_empty());
        assert!(matches!(
            &r.annotation_errors[0].problem,
            AnnotationProblem::Shape(s) if s.contains("names the kind of difference")
        ));
    }
    // the kind it covers: suppresses that difference
    let value = Annotation::new("SEC-1.3", at).covering(CoveredKind::Value);
    let r = check_with(&normalizer(), &a, &b, std::slice::from_ref(&value));
    assert_eq!(r.suppressed.len(), 1);
    // but not a missing header at the pointer it names
    let mut b = parts(&CAND);
    b.headers.remove(2);
    let r = check_with(
        &normalizer(),
        &a,
        &b,
        &[Annotation::new("SEC-1.3", "/http/0/head/headers/3").covering(CoveredKind::Value)],
    );
    assert!(!r.passed() && r.suppressed.is_empty());
    assert!(r
        .differences
        .iter()
        .any(|d| d.pointer == "/http/0/head/headers/3" && d.kind == DiffKind::Missing));
    // read from a list, the kind is checked
    let list = Annotation::list_from_json(&json!([
        {"deviation": "SEC-1.3", "pointer": at, "kind": "missing"}
    ]))
    .unwrap_or_else(|e| panic!("{e}"));
    assert_eq!(list[0].kind, Some(CoveredKind::Missing));
    assert!(Annotation::list_from_json(&json!([
        {"deviation": "SEC-1.3", "pointer": at, "kind": "every"}
    ]))
    .is_err());
}

// ------------------------------------------------------------------ top level only

#[test]
fn status_figures_are_volatile_at_the_top_level_only() {
    // at the top level and in the live block (live-elapsed), other values compare clean
    let live = |r: &Run| format!(", \"live\": {{\"elapsed_s\": {}}}", r.figs[0]);
    let (mut a, mut b) = (parts(&REF), parts(&CAND));
    set_body(&mut a, status_body(&REF, &live(&REF)));
    set_body(&mut b, status_body(&CAND, &live(&CAND)));
    expect_clean(&check(&a, &b));
    // the same names deeper in the body, under another parent or in an array element,
    // are compared exactly
    for (member, at) in [
        ("elapsed_s", "/http/0/content/value/job/elapsed_s"),
        ("tokens_per_s", "/http/0/content/value/job/tokens_per_s"),
        (
            "tokens_per_s_mean",
            "/http/0/content/value/job/tokens_per_s_mean",
        ),
        ("_done", "/http/0/content/value/job/_done"),
    ] {
        let nested = |v: &str| format!(", \"job\": {{\"{member}\": {v}}}");
        let (mut a, mut b) = (parts(&REF), parts(&CAND));
        set_body(&mut a, status_body(&REF, &nested("1731600008.25")));
        set_body(&mut b, status_body(&CAND, &nested("1800000008.25")));
        expect_diff(&check(&a, &b), at);
    }
    let (mut a, mut b) = (parts(&REF), parts(&CAND));
    set_body(
        &mut a,
        status_body(&REF, ", \"items\": [{\"elapsed_s\": 1.5}]"),
    );
    set_body(
        &mut b,
        status_body(&CAND, ", \"items\": [{\"elapsed_s\": 2.5}]"),
    );
    expect_diff(&check(&a, &b), "/http/0/content/value/items/0/elapsed_s");
}

#[test]
fn the_done_stamp_is_volatile_on_its_own_line_only() {
    // the root of each line of an answer's file: normalized (the fixture compares clean)
    expect_clean(&check(&parts(&REF), &parts(&CAND)));
    // a _done member inside a line's object is compared exactly
    let line = |r: &Run| format!("{{\"answer\": {{\"_done\": {}.25}}}}\n", r.t + 8);
    let (mut a, mut b) = (parts(&REF), parts(&CAND));
    a.files[0].1.push_str(&line(&REF));
    b.files[0].1.push_str(&line(&CAND));
    let r = check(&a, &b);
    assert!(!r.passed());
    assert!(
        pointers(&r).iter().any(|p| p.starts_with("/files/0/")),
        "{}",
        serde_json::to_string_pretty(&r.to_json()).unwrap_or_default()
    );
}
