//! CNF-04: the negative self-tests of the normalizer and the comparator.
//!
//! A reference observation, shaped like what project-maya writes (its exact headers, a
//! renamed model in a Content-Length-framed body, time and rate figures of different
//! widths), and a candidate observation that differs from it only in values the volatile
//! list names (ids, time stamps, figures, the `Date` and `Server` header values, the
//! port, the temporary directory) and in names the rename map decides, compare clean:
//! the shipped list derives the `Content-Length` value from the normalized body (lead
//! decision LD44, added by the CNF-04 follow-up); without that entry each
//! Content-Length-framed answer differs in that header, its raw head and its framing
//! length. Each test then mutates
//! one observable thing on the candidate side (a status, a header name, value, position,
//! a missing or an extra header, an event, an id cross-reference, a tape entry, a file
//! field, a log line, the exit status) and requires a difference at the expected pointer.
//! Each test is written so that it fails if the normalization it relies on were widened:
//! the mutated value is one a wider rule would swallow (a header name in another case, an
//! id in upper-case hex or one digit short, a time stamp outside the run window, an
//! integer turned into a fraction, a key at the right name under the wrong parent).
//!
//! No donor test method is re-expressed here: CNF-04 owns none. The shapes follow
//! project-maya serve/server.py:4936-4940, 5456-5463, 6600-6615, 3470-3471, 3490-3520 and
//! serve/model_api.py:57-58, 210-264 at 7e68a30f.

use std::path::PathBuf;

use console_conformance::compare::{
    compare, compare_documents, Annotation, AnnotationProblem, ApprovedIds, CoveredKind, DiffKind,
    IdStatus, Report,
};
use console_conformance::normalize::{Normalized, Normalizer, RunWindow, Side, SideContext};
use console_conformance::observe::{
    Content, End, Exchange, ExitRecord, FileRecord, Framing, Header, NdjsonParser, Observation,
    ResponseHead, SseParser,
};
use console_conformance::scenario::{
    load_rename_map, load_volatile_fields, Location, VolatileClass, VolatileFields,
};
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

fn normalizer_with(fields: &VolatileFields) -> Normalizer {
    let renames = load_rename_map(&contracts().join("rename-map.json"))
        .unwrap_or_else(|e| panic!("rename-map.json: {e}"));
    Normalizer::new(fields, renames).unwrap_or_else(|e| panic!("normalizer: {e}"))
}

fn normalizer() -> Normalizer {
    normalizer_with(&volatile())
}

fn approved() -> ApprovedIds {
    let text = std::fs::read_to_string(contracts().join("deviations.md"))
        .unwrap_or_else(|e| panic!("deviations.md: {e}"));
    ApprovedIds::from_register(&text).unwrap_or_else(|e| panic!("{e}"))
}

/// One response as the server would write it.
#[derive(Clone)]
struct Resp {
    version: String,
    code: u16,
    reason: String,
    headers: Vec<(String, String)>,
    body: Vec<u8>,
    /// Close-delimited (an event stream) instead of Content-Length.
    close: bool,
    /// The request body the client sent, when any (the same on both sides).
    request_body: Option<String>,
}

/// The run-dependent values of one side.
struct Run {
    t: u64,
    port: u16,
    tmp: &'static str,
    server: &'static str,
    date: &'static str,
    ids: [&'static str; 3],
    pid: u32,
    /// A time figure, an uptime, a metric value, the done line's elapsed time and rate:
    /// of different widths on the two sides, as Python writes measured values.
    figs: [&'static str; 5],
}

const REF: Run = Run {
    t: 1_731_600_000,
    port: 41_001,
    tmp: "/tmp/ref-run",
    server: "BaseHTTP/0.6 Python/3.14.7",
    date: "Thu, 14 Nov 2024 16:00:00 GMT",
    ids: [
        "0123456789abcdef01234567",
        "1111111111aaaaaaaaaa2222",
        "00aa11bb22cc33dd44ee55ff",
    ],
    pid: 4242,
    figs: ["12.25", "1234.5", "0.0005", "3", "12.5"],
};

const CAND: Run = Run {
    t: 1_800_000_000,
    port: 52_123,
    tmp: "/tmp/cand-run",
    server: "pulsar-console/0.1.0",
    date: "Fri, 15 Jan 2027 08:00:00 GMT",
    ids: [
        "fedcba9876543210fedcba98",
        "abcdefabcdefabcdefabcdef",
        "9999999999999999eeeeeeee",
    ],
    pid: 77,
    figs: ["3.5", "7.5", "0.00125", "0", "7.0"],
};

/// An item id the client chose, sent in the chat request on both sides.
const CLIENT_ITEM: &str = "item_aaaaaaaaaaaaaaaaaaaaaaaa";

fn window(r: &Run) -> RunWindow {
    RunWindow {
        start: r.t as f64,
        end: r.t as f64 + 60.0,
    }
}

fn ctx(r: &Run) -> SideContext {
    SideContext::new(window(r))
        .with_port(r.port)
        .with_tmp_dir(r.tmp)
}

fn std_headers(r: &Run, ctype: &str) -> Vec<(String, String)> {
    vec![
        ("Server".into(), r.server.into()),
        ("Date".into(), r.date.into()),
        ("Content-Type".into(), ctype.into()),
    ]
}

fn json_resp(r: &Run, body: String) -> Resp {
    Resp {
        version: "HTTP/1.0".into(),
        code: 200,
        reason: "OK".into(),
        headers: std_headers(r, "application/json"),
        body: body.into_bytes(),
        close: false,
        request_body: None,
    }
}

/// The observation of one side, before any mutation. `reference` selects the donor's
/// names (renamed by the comparator) instead of the console's.
struct Spec {
    http: Vec<Resp>,
    tape: Value,
    files: Vec<(String, String)>,
    log: Vec<String>,
    exit: Option<i32>,
}

fn spec(r: &Run, reference: bool) -> Spec {
    let t = r.t;
    let cid = format!("chatcmpl-{}", r.ids[0]);
    let sid = format!("chatcmpl-{}", r.ids[1]);
    let model = if reference {
        "qwen3.8-flash-next"
    } else {
        "pulsar-console-synthetic"
    };
    // a chat completion, as serve/server.py:5238 and the llama.cpp timings write it
    let chat = format!(
        "{{\"id\": \"{cid}\", \"object\": \"chat.completion\", \"created\": {}, \"model\": \"{model}\", \
         \"choices\": [{{\"index\": 0, \"message\": {{\"role\": \"assistant\", \"content\": \"Hi\"}}, \"finish_reason\": \"stop\"}}], \
         \"usage\": {{\"prompt_tokens\": 3, \"completion_tokens\": 1, \"total_tokens\": 4}}, \
         \"timings\": {{\"cache_n\": 0, \"prompt_n\": 3, \"prompt_ms\": {}, \"predicted_n\": 1, \"predicted_ms\": 2.{}}}}}",
        t + 1,
        r.figs[0],
        t % 10
    );
    // a stream, as serve/server.py:6600-6615 writes it: one id across every chunk
    let chunk = |content: &str| {
        format!(
            "data: {{\"id\": \"{sid}\", \"object\": \"chat.completion.chunk\", \"created\": {}, \"model\": \"{model}\", \
             \"choices\": [{{\"index\": 0, \"delta\": {{\"content\": \"{content}\"}}, \"finish_reason\": null}}]}}\n\n",
            t + 2
        )
    };
    let sse = format!(
        "{}: keep-alive\n\n{}data: [DONE]\n\n",
        chunk("Hel"),
        chunk("lo")
    );
    // the Ollama-shaped NDJSON of serve/model_api.py:210-264
    let stamp = |s: u64| {
        let secs = s % 86_400;
        format!(
            "{}T{:02}:{:02}:{:02}.123456Z",
            if r.t == REF.t {
                "2024-11-14"
            } else {
                "2027-01-15"
            },
            secs / 3600,
            (secs / 60) % 60,
            secs % 60
        )
    };
    let day0 = if r.t == REF.t {
        1_731_542_400
    } else {
        1_800_000_000 - 28_800
    };
    let ndjson = format!(
        "{{\"model\": \"m\", \"created_at\": \"{}\", \"message\": {{\"role\": \"assistant\", \"content\": \"Hi\"}}, \"done\": false}}\n\
         {{\"model\": \"m\", \"created_at\": \"{}\", \"done\": true, \"done_reason\": \"stop\", \"total_duration\": {}, \
         \"load_duration\": 0, \"prompt_eval_count\": 3, \"prompt_eval_duration\": {}, \"eval_count\": 1, \"eval_duration\": {}}}\n",
        stamp(t + 3 - day0),
        stamp(t + 4 - day0),
        100_000_000 + t % 1000,
        40_000_000 + t % 100,
        60_000_000 + t % 10
    );
    // Prometheus text, as serve/server.py:3470-3471 writes it
    let metrics = format!(
        "# HELP llamacpp:prompt_tokens_total Prompt tokens read\n# TYPE llamacpp:prompt_tokens_total counter\n\
         llamacpp:prompt_tokens_total 3\n\
         # HELP llamacpp:prompt_seconds_total Prompt read time\n# TYPE llamacpp:prompt_seconds_total counter\n\
         llamacpp:prompt_seconds_total {}\n",
        r.figs[2]
    );
    // GET /v1/status and GET /api/port (serve/server.py:3490-3520, 2873)
    let status = format!(
        "{{\"service\": \"svc\", \"started\": {t}, \"uptime_s\": {}, \
         \"activity\": {{\"queue\": {{\"waiting\": 0, \"first_waited_s\": 0.{}, \"places\": 1}}, \"last_request_at\": {}}}, \
         \"machine\": {{\"at\": {}, \"gpu\": null}}, \"port\": {}}}",
        r.figs[1],
        t % 10,
        t + 5,
        t + 6,
        r.port
    );
    let mut stream = Resp {
        version: "HTTP/1.0".into(),
        code: 200,
        reason: "OK".into(),
        headers: vec![
            ("Server".into(), r.server.into()),
            ("Date".into(), r.date.into()),
            ("Content-Type".into(), "text/event-stream".into()),
            ("Cache-Control".into(), "no-cache".into()),
        ],
        body: sse.into_bytes(),
        close: true,
        request_body: None,
    };
    // exactly the headers of _sse (serve/server.py:6471-6474) and _ndjson_start
    // (5629-5631): no Connection header, and Cache-Control on both
    stream.headers.truncate(4);
    let mut ollama = json_resp(r, ndjson);
    ollama.headers = std_headers(r, "application/x-ndjson");
    ollama
        .headers
        .push(("Cache-Control".into(), "no-cache".into()));
    ollama.close = true;
    // the chat request carries an item id the client chose (serve/responses.py:133)
    let mut chat_resp = json_resp(r, chat);
    chat_resp.request_body = Some(format!(
        "{{\"model\": \"m\", \"input\": [{{\"id\": \"{CLIENT_ITEM}\", \"role\": \"user\"}}]}}"
    ));
    let mut prom = json_resp(r, metrics);
    prom.headers = std_headers(r, "text/plain; version=0.0.4; charset=utf-8");

    let switch_name = if reference {
        ".maya-switch.json"
    } else {
        ".pulsar-switch.json"
    };
    let config_name = if reference {
        "maya-a.json"
    } else {
        "pulsar-a.json"
    };
    let note = format!(
        "{{\"config\": \"{}/configs/{config_name}\", \"port\": {}, \"why\": \"switch\", \"time\": {}.{}}}",
        r.tmp,
        r.port,
        t + 7,
        t % 1000
    );
    let answers = format!(
        "{{\"id\": \"{sid}\", \"object\": \"chat.completion.chunk\", \"created\": {}}}\n{{\"_done\": {}.25}}\n",
        t + 2,
        t + 8
    );
    let prefix = if reference { "[maya] " } else { "[console] " };
    let env = if reference {
        "MAYA_MAX_BODY_MIB"
    } else {
        "PULSAR_CONSOLE_MAX_BODY_MIB"
    };
    Spec {
        http: vec![chat_resp, stream, ollama, prom, json_resp(r, status)],
        tape: json!([{"op": "generate", "prompt": [1, 2, 3], "max_tokens": 16}]),
        files: vec![
            (format!("models/{switch_name}"), note),
            (format!("answers/{sid}.jsonl"), answers),
            (
                format!("state/kept-{}.json", r.pid),
                "{\"kept\": true}".to_string(),
            ),
        ],
        log: vec![
            format!(
                "ready: http://127.0.0.1:{}/v1  (OpenAI: /v1/chat/completions)",
                r.port
            ),
            format!("{prefix}the request body is larger than 1 MiB ({env} raises the limit)"),
            format!(
                "{prefix}done: 1 tokens in {} s ({} tok/s) (stop, cancel=False)",
                r.figs[3], r.figs[4]
            ),
        ],
        exit: Some(0),
    }
}

fn exchange(r: &Resp) -> Exchange {
    let mut headers = r.headers.clone();
    if !r.close {
        headers.push(("Content-Length".into(), r.body.len().to_string()));
    }
    let mut raw = format!("{} {} {}\r\n", r.version, r.code, r.reason).into_bytes();
    for (n, v) in &headers {
        raw.extend_from_slice(format!("{n}: {v}\r\n").as_bytes());
    }
    raw.extend_from_slice(b"\r\n");
    let head = ResponseHead {
        version: r.version.clone(),
        code: r.code,
        reason: r.reason.clone(),
        headers: headers
            .iter()
            .map(|(n, v)| Header {
                name: n.clone(),
                value: v.clone(),
            })
            .collect(),
        raw: raw.clone(),
    };
    let content = match head.media_type().as_deref() {
        Some("application/json") => match serde_json::from_slice(&r.body) {
            Ok(v) => Content::Json(v),
            Err(e) => Content::InvalidJson(e.to_string()),
        },
        Some("text/event-stream") => {
            let mut p = SseParser::new();
            p.feed(&r.body, None);
            Content::Sse(p.finish())
        }
        Some("application/x-ndjson") => {
            let mut p = NdjsonParser::new();
            p.feed(&r.body, None);
            Content::Ndjson(p.finish())
        }
        _ => Content::Opaque,
    };
    let request = match &r.request_body {
        Some(b) => format!(
            "POST /v1/responses HTTP/1.0\r\nContent-Length: {}\r\n\r\n{b}",
            b.len()
        )
        .into_bytes(),
        None => b"GET / HTTP/1.0\r\n\r\n".to_vec(),
    };
    let mut wire = raw;
    wire.extend_from_slice(&r.body);
    Exchange {
        request_sent: request.len() as u64,
        request,
        write_error: None,
        interim: Vec::new(),
        head: Some(head),
        framing: Some(if r.close {
            Framing::CloseDelimited
        } else {
            Framing::ContentLength(r.body.len() as u64)
        }),
        body: r.body.clone(),
        content,
        end: End::Complete,
        server_closed: Some(true),
        disconnect: None,
        wire,
    }
}

fn build(s: &Spec) -> Value {
    Observation {
        http: s.http.iter().map(exchange).collect(),
        engine_tape: Some(s.tape.clone()),
        files: s
            .files
            .iter()
            .map(|(p, b)| FileRecord::from_bytes(p, b.clone().into_bytes()))
            .collect(),
        log: s.log.clone(),
        exit: s.exit.map(|c| ExitRecord {
            code: Some(c),
            signal: None,
        }),
    }
    .to_json()
}

fn check(candidate: &Spec, annotations: &[Annotation]) -> Report {
    check_with(&normalizer(), candidate, annotations)
}

fn check_with(n: &Normalizer, candidate: &Spec, annotations: &[Annotation]) -> Report {
    compare_documents(
        n,
        &build(&spec(&REF, true)),
        &ctx(&REF),
        &build(candidate),
        &ctx(&CAND),
        annotations,
        &approved(),
    )
    .unwrap_or_else(|e| panic!("normalize: {e}"))
}

fn check_pair(reference: &Spec, candidate: &Spec) -> Report {
    check_pair_with(&normalizer(), reference, candidate)
}

fn check_pair_with(n: &Normalizer, reference: &Spec, candidate: &Spec) -> Report {
    compare_documents(
        n,
        &build(reference),
        &ctx(&REF),
        &build(candidate),
        &ctx(&CAND),
        &[],
        &approved(),
    )
    .unwrap_or_else(|e| panic!("normalize: {e}"))
}

fn cand() -> Spec {
    spec(&CAND, false)
}

/// The shipped list, which holds the derived Content-Length entry since the CNF-04
/// follow-up (LD44): checked here, so that the tests that rely on it fail if it goes.
fn with_content_length() -> VolatileFields {
    let list = volatile();
    assert!(
        list.fields.iter().any(|f| f.id == "header-content-length"
            && f.class == VolatileClass::BodyLength
            && matches!(&f.location, Location::Header { name } if name == "Content-Length")),
        "the shipped list has no derived Content-Length entry"
    );
    list
}

/// The shipped list without its Content-Length entry: the value is compared as sent.
fn without_content_length() -> VolatileFields {
    let mut list = volatile();
    list.fields.retain(|f| f.id != "header-content-length");
    list
}

fn cl_normalizer() -> Normalizer {
    normalizer_with(&with_content_length())
}

/// Compares with the shipped list, whose derived Content-Length entry makes the
/// unmutated fixture compare clean.
fn check_cl(candidate: &Spec, annotations: &[Annotation]) -> Report {
    check_with(&cl_normalizer(), candidate, annotations)
}

/// Compares with the shipped list less its Content-Length entry.
fn check_without_cl(candidate: &Spec) -> Report {
    check_with(&normalizer_with(&without_content_length()), candidate, &[])
}

/// The exchanges framed by Content-Length whose length differs between the sides.
const CL_EXCHANGES: [usize; 3] = [0, 3, 4];

/// What the unmutated fixture differs in without the Content-Length entry: the
/// Content-Length value, the raw head that holds it and the framing length of each such
/// exchange. A mutation test must not rely on a difference there.
fn baseline_pointers() -> Vec<String> {
    let mut out = Vec::new();
    for i in CL_EXCHANGES {
        out.push(format!("/http/{i}/head/headers/3/1"));
        out.push(format!("/http/{i}/head/raw/text"));
        out.push(format!("/http/{i}/framing/length"));
    }
    out
}

/// The pointers of the unsuppressed differences.
fn pointers(r: &Report) -> Vec<String> {
    r.differences.iter().map(|d| d.pointer.clone()).collect()
}

/// Requires a failing report with a difference at `pointer`, a pointer at which the
/// unmutated fixture does not already differ.
fn expect_diff(r: &Report, pointer: &str) {
    assert!(
        !baseline_pointers().iter().any(|p| p == pointer),
        "{pointer} differs in the unmutated fixture already"
    );
    expect_diff_anywhere(r, pointer);
}

/// Requires a failing report with a difference at `pointer`.
fn expect_diff_anywhere(r: &Report, pointer: &str) {
    assert!(
        !r.passed(),
        "expected a difference at {pointer}, the report passed"
    );
    assert!(
        pointers(r).iter().any(|p| p == pointer),
        "no difference at {pointer}; got {}",
        serde_json::to_string_pretty(&r.to_json()).unwrap_or_default()
    );
}

fn replace_body(s: &mut Spec, i: usize, from: &str, to: &str) {
    let text = String::from_utf8(s.http[i].body.clone()).unwrap_or_default();
    assert!(text.contains(from), "body {i} has no {from:?}");
    s.http[i].body = text.replacen(from, to, 1).into_bytes();
}

// ------------------------------------------------------------------ positive controls

#[test]
fn observations_that_differ_only_in_volatile_values_compare_clean_apart_from_content_length() {
    // changed by the CNF-04 follow-up: the shipped list now derives Content-Length, so
    // the exact comparison of that value is shown with the entry removed. Without it, a
    // renamed model and figures of other widths change the length of each
    // Content-Length-framed answer
    let r = check_without_cl(&cand());
    let mut got = pointers(&r);
    got.sort();
    let mut want = baseline_pointers();
    want.sort();
    assert_eq!(
        got,
        want,
        "{}",
        serde_json::to_string_pretty(&r.to_json()).unwrap_or_default()
    );
    // with the shipped list, whose Content-Length entry is derived from the normalized
    // body, they compare clean
    let r = check(&cand(), &[]);
    assert!(
        r.clean(),
        "{}",
        serde_json::to_string_pretty(&r.to_json()).unwrap_or_default()
    );
}

#[test]
fn every_replacement_traces_to_a_listed_field_or_a_rename() {
    let n = normalizer();
    let list = volatile();
    for (s, side, c) in [
        (spec(&REF, true), Side::Reference, ctx(&REF)),
        (cand(), Side::Candidate, ctx(&CAND)),
    ] {
        let out = n
            .normalize(&build(&s), side, &c)
            .unwrap_or_else(|e| panic!("{e}"));
        assert!(out.issues.is_empty(), "{:?}", out.issues);
        assert!(!out.applied.is_empty());
        for a in &out.applied {
            if let Some(id) = a.source.strip_prefix("volatile:") {
                assert!(list.fields.iter().any(|f| f.id == id), "{id}");
            } else if let Some(dev) = a.source.strip_prefix("rename:") {
                assert_eq!(side, Side::Reference, "the candidate side is never renamed");
                assert!(approved().is_approved(dev), "{dev}");
            } else {
                panic!("an untraced replacement: {a:?}");
            }
        }
        // the volatile values of both header kinds, ids, stamps, figures, the port, the
        // temporary directory, the process id, the metric and the NDJSON durations were
        // all replaced
        for id in [
            "header-date",
            "header-server",
            "id-chat-completion",
            "created-chat-completion",
            "created-at-ndjson",
            "ndjson-total-duration",
            "metric-prompt-seconds",
            "status-started",
            "uptime",
            "queue-first-waited",
            "status-last-request-at",
            "status-machine-at",
            "port-api-port",
            "port-ready-line",
            "tmp-note-config-path",
            "snapshot-time",
            "pid-kept-file",
            "id-answer-file",
            "answer-done",
            "prompt-ms",
            "timings-predicted-ms",
            "log-done-figures",
        ] {
            assert!(
                out.applied
                    .iter()
                    .any(|a| a.source == format!("volatile:{id}")),
                "{side:?}: {id} was not applied"
            );
        }
    }
}

// ------------------------------------------------------------------ status line

#[test]
fn a_mutated_status_code_is_a_difference() {
    let mut c = cand();
    c.http[0].code = 201;
    expect_diff(&check(&c, &[]), "/http/0/head/code");
}

#[test]
fn a_mutated_reason_phrase_is_a_difference() {
    let mut c = cand();
    c.http[0].reason = "Ok".into();
    expect_diff(&check(&c, &[]), "/http/0/head/reason");
}

#[test]
fn a_mutated_http_version_token_is_a_difference() {
    let mut c = cand();
    c.http[1].version = "HTTP/1.1".into();
    expect_diff(&check(&c, &[]), "/http/1/head/version");
}

// ------------------------------------------------------------------ headers

#[test]
fn a_header_name_in_another_case_is_a_difference() {
    // Date's value is volatile, its name is not: a case-insensitive name rule would
    // swallow this.
    let mut c = cand();
    c.http[0].headers[1].0 = "date".into();
    let r = check(&c, &[]);
    expect_diff(&r, "/http/0/head/headers/1/0");
}

#[test]
fn a_mutated_header_value_is_a_difference() {
    let mut c = cand();
    c.http[0].headers[2].1 = "application/json; charset=utf-8".into();
    expect_diff(&check(&c, &[]), "/http/0/head/headers/2/1");
}

#[test]
fn headers_in_another_order_are_a_difference() {
    // Server and Date swap places: both values are volatile, the positions are not.
    let mut c = cand();
    c.http[0].headers.swap(0, 1);
    let r = check(&c, &[]);
    expect_diff(&r, "/http/0/head/headers/0/0");
    expect_diff(&r, "/http/0/head/headers/1/0");
}

#[test]
fn a_missing_header_is_a_difference() {
    let mut c = cand();
    c.http[1].headers.retain(|(n, _)| n != "Cache-Control");
    let r = check(&c, &[]);
    expect_diff(&r, "/http/1/head/headers/3");
    assert!(r.differences.iter().any(|d| d.kind == DiffKind::Missing));
}

#[test]
fn a_missing_date_header_is_a_difference() {
    let mut c = cand();
    c.http[0].headers.retain(|(n, _)| n != "Date");
    expect_diff(&check(&c, &[]), "/http/0/head/headers/1/0");
}

#[test]
fn an_extra_header_is_a_difference() {
    let mut c = cand();
    c.http[0].headers.push(("X-Request-Id".into(), "1".into()));
    let r = check(&c, &[]);
    expect_diff(&r, "/http/0/head/headers/4");
    assert!(r.differences.iter().any(|d| d.kind == DiffKind::Extra));
}

#[test]
fn a_repeated_volatile_header_is_not_normalized() {
    // "present once" is part of the header-value check: a second Date header keeps
    // both values as sent.
    let mut c = cand();
    c.http[0]
        .headers
        .insert(2, ("Date".into(), CAND.date.into()));
    let r = check(&c, &[]);
    expect_diff(&r, "/http/0/head/headers/1/1");
}

#[test]
fn an_empty_server_value_is_a_difference() {
    let mut c = cand();
    c.http[0].headers[0].1 = String::new();
    expect_diff(&check(&c, &[]), "/http/0/head/headers/0/1");
}

#[test]
fn a_content_length_that_differs_is_a_difference() {
    // even with a derived Content-Length entry, a body one byte longer shows in the
    // header, the framing and the body
    let mut c = cand();
    replace_body(&mut c, 0, "\"Hi\"", "\"Hi!\"");
    let r = check_cl(&c, &[]);
    expect_diff_anywhere(&r, "/http/0/head/headers/3/1");
    expect_diff_anywhere(&r, "/http/0/framing/length");
    expect_diff(&r, "/http/0/body/text");
}

#[test]
fn a_date_value_not_in_http_date_form_or_outside_the_run_is_a_difference() {
    // Python writes an IMF-fixdate (serve/server.py:5459, send_response); only the
    // moment is volatile. CAND's window is 08:00:00 to 08:01:00 on that day.
    for bad in [
        "2027-01-15T08:00:00Z",
        "yesterday",
        "Fri, 15 Jan 2027 09:30:00 GMT",
        "Sat, 15 Jan 2027 08:00:00 GMT",
        "Fri, 15 Jan 2027 08:00:00 UTC",
    ] {
        let mut c = cand();
        for resp in &mut c.http {
            for (n, v) in &mut resp.headers {
                if n == "Date" {
                    *v = bad.into();
                }
            }
        }
        let r = check(&c, &[]);
        expect_diff(&r, "/http/0/head/headers/1/1");
        expect_diff(&r, "/http/1/head/headers/1/1");
    }
    // a Date inside the run, at another second, is volatile
    let mut c = cand();
    c.http[1].headers[1].1 = "Fri, 15 Jan 2027 08:00:59 GMT".into();
    assert!(!pointers(&check(&c, &[]))
        .iter()
        .any(|p| p.starts_with("/http/1/head")));
}

// ------------------------------------------------------------------ bodies

#[test]
fn json_key_order_is_a_difference() {
    let mut c = cand();
    replace_body(
        &mut c,
        0,
        "\"object\": \"chat.completion\", \"created\"",
        "\"created\"",
    );
    let text = String::from_utf8(c.http[0].body.clone()).unwrap_or_default();
    c.http[0].body = text
        .replacen("\"id\":", "\"object\": \"chat.completion\", \"id\":", 1)
        .into_bytes();
    let r = check(&c, &[]);
    expect_diff(&r, "/http/0/content/value");
    assert!(r.differences.iter().any(|d| d.kind == DiffKind::KeyOrder));
}

#[test]
fn json_white_space_is_a_difference() {
    // the same document with Python's separators replaced: the parsed values agree,
    // the body text does not
    let mut c = cand();
    replace_body(&mut c, 0, "\"object\": ", "\"object\":");
    let r = check(&c, &[]);
    expect_diff(&r, "/http/0/body/text");
    assert!(!pointers(&r)
        .iter()
        .any(|p| p.starts_with("/http/0/content")));
}

#[test]
fn an_escape_in_place_of_a_character_is_a_difference() {
    let mut c = cand();
    replace_body(
        &mut c,
        0,
        "\"content\": \"Hi\"",
        "\"content\": \"H\\u0069\"",
    );
    expect_diff(&check(&c, &[]), "/http/0/body/text");
}

#[test]
fn a_volatile_figure_turned_from_a_fraction_into_an_integer_is_a_difference() {
    let mut c = cand();
    let ms = format!("\"prompt_ms\": {}", CAND.figs[0]);
    replace_body(&mut c, 0, &ms, "\"prompt_ms\": 1");
    let r = check(&c, &[]);
    expect_diff(&r, "/http/0/content/value/timings/prompt_ms");
}

#[test]
fn a_negative_volatile_figure_is_a_difference() {
    let mut c = cand();
    let ms = format!("\"prompt_ms\": {}", CAND.figs[0]);
    replace_body(&mut c, 0, &ms, "\"prompt_ms\": -1.5");
    expect_diff(&check(&c, &[]), "/http/0/content/value/timings/prompt_ms");
}

#[test]
fn a_count_beside_the_timing_figures_is_not_volatile() {
    let mut c = cand();
    replace_body(&mut c, 0, "\"prompt_n\": 3", "\"prompt_n\": 4");
    expect_diff(&check(&c, &[]), "/http/0/content/value/timings/prompt_n");
}

#[test]
fn a_created_stamp_outside_the_run_window_is_a_difference() {
    let mut c = cand();
    replace_body(
        &mut c,
        0,
        &format!("\"created\": {}", CAND.t + 1),
        &format!("\"created\": {}", CAND.t + 3600),
    );
    expect_diff(&check(&c, &[]), "/http/0/content/value/created");
}

#[test]
fn a_created_stamp_written_as_a_fraction_or_a_string_is_a_difference() {
    for to in [format!("{}.5", CAND.t + 1), format!("\"{}\"", CAND.t + 1)] {
        let mut c = cand();
        replace_body(
            &mut c,
            0,
            &format!("\"created\": {}", CAND.t + 1),
            &format!("\"created\": {to}"),
        );
        expect_diff(&check(&c, &[]), "/http/0/content/value/created");
    }
}

#[test]
fn an_id_in_upper_case_or_of_another_length_is_a_difference() {
    for to in [
        "chatcmpl-FEDCBA9876543210FEDCBA98",
        "chatcmpl-fedcba9876543210fedcba9",
    ] {
        let mut c = cand();
        replace_body(&mut c, 0, &format!("chatcmpl-{}", CAND.ids[0]), to);
        expect_diff(&check(&c, &[]), "/http/0/content/value/id");
    }
}

#[test]
fn a_broken_id_cross_reference_is_a_difference() {
    // the second chunk of the stream carries a fresh id instead of the first chunk's
    let mut c = cand();
    let text = String::from_utf8(c.http[1].body.clone()).unwrap_or_default();
    let sid = format!("chatcmpl-{}", CAND.ids[1]);
    let at = text.rfind(&sid).unwrap_or(0);
    let mut changed = text.clone();
    changed.replace_range(at..at + sid.len(), &format!("chatcmpl-{}", CAND.ids[2]));
    c.http[1].body = changed.into_bytes();
    let r = check(&c, &[]);
    expect_diff(&r, "/http/1/content/events/1/json/id");
    let d = r
        .differences
        .iter()
        .find(|d| d.pointer == "/http/1/content/events/1/json/id");
    assert_eq!(
        d.and_then(|d| d.reference.clone()),
        Some(json!("<chatcmpl-#2>"))
    );
    assert_eq!(
        d.and_then(|d| d.candidate.clone()),
        Some(json!("<chatcmpl-#3>"))
    );
}

#[test]
fn an_id_shared_between_a_stream_and_a_file_name_is_cross_checked() {
    // the answers file is named after the stream's id; a file named after another id
    // is a difference
    let mut c = cand();
    c.files[1].0 = format!("answers/chatcmpl-{}.jsonl", CAND.ids[2]);
    expect_diff(&check(&c, &[]), "/files/0/path");
}

#[test]
fn a_mutated_event_is_a_difference() {
    let mut c = cand();
    replace_body(&mut c, 1, "\"content\": \"lo\"", "\"content\": \"lO\"");
    expect_diff(
        &check(&c, &[]),
        "/http/1/content/events/1/json/choices/0/delta/content",
    );
}

#[test]
fn a_missing_or_extra_event_is_a_difference() {
    let mut c = cand();
    replace_body(&mut c, 1, "data: [DONE]\n\n", "");
    expect_diff(&check(&c, &[]), "/http/1/content/events/2");
    let mut c = cand();
    replace_body(
        &mut c,
        1,
        "data: [DONE]\n\n",
        "data: [DONE]\n\ndata: [DONE]\n\n",
    );
    expect_diff(&check(&c, &[]), "/http/1/content/events/3");
}

#[test]
fn an_event_name_field_is_a_difference() {
    let mut c = cand();
    replace_body(&mut c, 1, "data: [DONE]", "event: done\ndata: [DONE]");
    expect_diff(&check(&c, &[]), "/http/1/content/events/2/event");
}

#[test]
fn stream_framing_is_a_difference() {
    // CRLF line ends instead of LF, a missing keep-alive comment, an unterminated end
    let mut c = cand();
    let text = String::from_utf8(c.http[1].body.clone()).unwrap_or_default();
    c.http[1].body = text.replace("\n\n", "\r\n\r\n").into_bytes();
    expect_diff(&check(&c, &[]), "/http/1/body/text");

    let mut c = cand();
    replace_body(&mut c, 1, ": keep-alive\n\n", "");
    expect_diff(&check(&c, &[]), "/http/1/content/comments/0");

    let mut c = cand();
    replace_body(&mut c, 1, "data: [DONE]\n\n", "data: [DONE]\n");
    expect_diff(&check(&c, &[]), "/http/1/content/unterminated");
}

#[test]
fn a_mutated_ndjson_line_is_a_difference() {
    let mut c = cand();
    replace_body(
        &mut c,
        2,
        "\"done_reason\": \"stop\"",
        "\"done_reason\": \"length\"",
    );
    expect_diff(&check(&c, &[]), "/http/2/content/lines/1/json/done_reason");
}

#[test]
fn an_iso_stamp_in_another_format_is_a_difference() {
    // three fraction digits instead of Python's six
    let mut c = cand();
    replace_body(&mut c, 2, ".123456Z", ".123Z");
    expect_diff(&check(&c, &[]), "/http/2/content/lines/0/json/created_at");
}

#[test]
fn a_metric_that_is_not_listed_is_compared_exactly() {
    let mut c = cand();
    replace_body(
        &mut c,
        3,
        "llamacpp:prompt_tokens_total 3",
        "llamacpp:prompt_tokens_total 4",
    );
    expect_diff(&check(&c, &[]), "/http/3/body/text");
    let mut c = cand();
    replace_body(
        &mut c,
        3,
        "# HELP llamacpp:prompt_seconds_total Prompt read time",
        "# HELP llamacpp:prompt_seconds_total Prompt time",
    );
    expect_diff(&check(&c, &[]), "/http/3/body/text");
}

#[test]
fn a_volatile_key_under_the_wrong_parent_is_compared_exactly() {
    // `at` is volatile only under `machine` and `last_timings`
    let mut c = cand();
    replace_body(
        &mut c,
        4,
        &format!("\"machine\": {{\"at\": {}", CAND.t + 6),
        &format!("\"machine2\": {{\"at\": {}", CAND.t + 6),
    );
    let r = check(&c, &[]);
    expect_diff(&r, "/http/4/content/value/machine2");
    expect_diff(&r, "/http/4/content/value/machine");
}

#[test]
fn a_volatile_key_name_under_an_unlisted_parent_is_compared_exactly() {
    // `at` (a stamp) and `tok_s` (a rate) are volatile only under the parents the list
    // names; under another parent both sides' in-window values stay as sent
    let mut a = spec(&REF, true);
    let mut b = cand();
    let add = |s: &mut Spec, t: u64, rate: &str| {
        replace_body(
            s,
            4,
            "\"service\": \"svc\"",
            &format!(
                "\"service\": \"svc\", \"other\": {{\"at\": {}, \"tok_s\": {rate}}}",
                t + 6
            ),
        )
    };
    add(&mut a, REF.t, "1.5");
    add(&mut b, CAND.t, "2.5");
    let r = check_pair(&a, &b);
    expect_diff(&r, "/http/4/content/value/other/at");
    expect_diff(&r, "/http/4/content/value/other/tok_s");
    // under the listed parent, different values of the same key are volatile
    let mut a = spec(&REF, true);
    let mut b = cand();
    let add = |s: &mut Spec, rate: &str| {
        replace_body(
            s,
            4,
            "\"service\": \"svc\"",
            &format!("\"service\": \"svc\", \"live\": {{\"tok_s\": {rate}}}"),
        )
    };
    add(&mut a, "1.5");
    add(&mut b, "2.5");
    let r = check_pair_with(&cl_normalizer(), &a, &b);
    assert!(
        r.clean(),
        "{}",
        serde_json::to_string_pretty(&r.to_json()).unwrap_or_default()
    );
}

#[test]
fn a_port_that_is_not_the_servers_is_compared_exactly() {
    let mut c = cand();
    replace_body(
        &mut c,
        4,
        &format!("\"port\": {}", CAND.port),
        "\"port\": 8000",
    );
    expect_diff(&check(&c, &[]), "/http/4/content/value/port");
}

// ------------------------------------------------------------------ exchange record

#[test]
fn how_the_read_ended_and_the_close_are_observable() {
    let s = cand();
    let mut v = build(&s);
    v["http"][0]["end"] = json!({"kind": "truncated"});
    v["http"][0]["server_closed"] = json!(false);
    let r = compare_documents(
        &normalizer(),
        &build(&spec(&REF, true)),
        &ctx(&REF),
        &v,
        &ctx(&CAND),
        &[],
        &approved(),
    )
    .unwrap_or_else(|e| panic!("{e}"));
    expect_diff(&r, "/http/0/end/kind");
    expect_diff(&r, "/http/0/server_closed");
}

#[test]
fn wire_bytes_past_the_body_are_a_difference() {
    let s = cand();
    let mut v = build(&s);
    let ex = exchange(&s.http[0]);
    let mut wire = ex.wire.clone();
    wire.extend_from_slice(b"junk");
    v["http"][0]["wire"] = console_conformance::observe::bytes_json(&wire);
    let r = compare_documents(
        &normalizer(),
        &build(&spec(&REF, true)),
        &ctx(&REF),
        &v,
        &ctx(&CAND),
        &[],
        &approved(),
    )
    .unwrap_or_else(|e| panic!("{e}"));
    expect_diff(&r, "/http/0/wire");
}

// ------------------------------------------------------------------ tape, files, log, exit

#[test]
fn a_mutated_tape_entry_is_a_difference() {
    let mut c = cand();
    c.tape = json!([{"op": "generate", "prompt": [1, 2, 4], "max_tokens": 16}]);
    expect_diff(&check(&c, &[]), "/engine_tape/0/prompt/2");
    let mut c = cand();
    c.tape = json!([{"op": "generate", "prompt": [1, 2, 3], "max_tokens": 16}, {"op": "stop"}]);
    expect_diff(&check(&c, &[]), "/engine_tape/1");
}

#[test]
fn a_mutated_file_field_is_a_difference() {
    let mut c = cand();
    c.files[0].1 = c.files[0]
        .1
        .replace("\"why\": \"switch\"", "\"why\": \"delete\"");
    let r = check(&c, &[]);
    expect_diff(&r, "/files/1/json/why");
    expect_diff(&r, "/files/1/bytes/text");
}

#[test]
fn a_file_path_outside_the_temporary_directory_is_a_difference() {
    let mut c = cand();
    c.files[0].1 = c.files[0].1.replace(CAND.tmp, "/var/elsewhere");
    expect_diff(&check(&c, &[]), "/files/1/json/config");
}

#[test]
fn a_missing_or_renamed_file_is_a_difference() {
    let mut c = cand();
    c.files.remove(2);
    expect_diff(&check(&c, &[]), "/files/2");
    let mut c = cand();
    c.files[0].0 = "models/.maya-switch.json".into();
    let r = check(&c, &[]);
    assert!(!r.passed());
    assert!(pointers(&r).iter().any(|p| p.ends_with("/path")));
}

#[test]
fn a_mutated_log_line_is_a_difference() {
    let mut c = cand();
    c.log[1] = c.log[1].replace("1 MiB", "2 MiB");
    expect_diff(&check(&c, &[]), "/log/1");
    // the donor's prefix is renamed on the reference side only: a candidate that
    // writes the donor's prefix differs
    let mut c = cand();
    c.log[1] = c.log[1].replace("[console] ", "[maya] ");
    expect_diff(&check(&c, &[]), "/log/1");
    // a variable name that only contains a renamed one is not renamed
    let mut c = cand();
    c.log[1] = c.log[1].replace(
        "PULSAR_CONSOLE_MAX_BODY_MIB",
        "PULSAR_CONSOLE_MAX_BODY_MIBS",
    );
    expect_diff(&check(&c, &[]), "/log/1");
}

#[test]
fn a_ready_line_with_another_port_is_a_difference() {
    let mut c = cand();
    c.log[0] = c.log[0].replace(&CAND.port.to_string(), "8000");
    expect_diff(&check(&c, &[]), "/log/0");
}

#[test]
fn a_mutated_exit_status_is_a_difference() {
    let mut c = cand();
    c.exit = Some(1);
    expect_diff(&check(&c, &[]), "/exit/code");
}

#[test]
fn placeholder_text_in_an_observation_is_a_difference() {
    let mut c = cand();
    replace_body(&mut c, 0, "\"content\": \"Hi\"", "\"content\": \"<num>\"");
    let r = check(&c, &[]);
    assert!(r
        .differences
        .iter()
        .any(|d| d.kind == DiffKind::Normalization(Side::Candidate)));
}

// ------------------------------------------------------------------ annotations

#[test]
fn an_approved_annotation_suppresses_exactly_its_difference() {
    let mut c = cand();
    c.http[0].headers[2].1 = "application/json; charset=utf-8".into();
    let a = Annotation::new("SEC-1.3", "/http/0/head/headers/2/1").expecting(
        Some(json!("application/json")),
        Some(json!("application/json; charset=utf-8")),
    );
    let r = check_cl(&c, std::slice::from_ref(&a));
    // the raw head still differs: an annotation covers one pointer
    assert_eq!(r.suppressed.len(), 1);
    expect_diff_anywhere(&r, "/http/0/head/raw/text");
    // (CNF-04F: an annotation without both values names the kind it covers)
    let raw = Annotation::new("SEC-1.3", "/http/0/head/raw/text").covering(CoveredKind::Text);
    let r = check_cl(&c, &[a, raw]);
    assert!(
        r.clean(),
        "{}",
        serde_json::to_string_pretty(&r.to_json()).unwrap_or_default()
    );
    assert_eq!(r.suppressed.len(), 2);
    assert!(r.suppressed.iter().all(|s| s.deviation == "SEC-1.3"));
}

#[test]
fn annotations_citing_ids_that_are_not_approved_fail() {
    let mut c = cand();
    c.http[0].headers[2].1 = "text/json".into();
    for id in [
        "P-5", "P-12", "P-17", "P-18", "P-19", "P-20", "P-21", "P-22", "P-23", "P-24", "P-25",
        "P-26", "SEC-8",
    ] {
        // (CNF-04F: a well-shaped annotation, so that only the approval check refuses it)
        let r = check_cl(
            &c,
            &[Annotation::new(id, "/http/0/head/headers/2/1").covering(CoveredKind::Value)],
        );
        assert!(!r.passed(), "{id}");
        assert_eq!(r.annotation_errors.len(), 1, "{id}");
        assert!(r.suppressed.is_empty(), "{id}");
        assert!(matches!(
            r.annotation_errors[0].problem,
            AnnotationProblem::NotApproved(
                IdStatus::Declined | IdStatus::AwaitingOwner | IdStatus::Unknown
            )
        ));
    }
}

#[test]
fn an_unused_annotation_is_reported() {
    let r = check_cl(
        &cand(),
        &[Annotation::new("P-1", "/http/0/head/headers/0/1").covering(CoveredKind::Value)],
    );
    assert!(r.passed());
    assert!(!r.clean());
    assert_eq!(r.unused_annotations, [0]);
}

#[test]
fn a_proposed_rename_is_hinted_but_not_applied() {
    // the console's metric prefix is proposed (BRAND-1.6), so the reference's `maya:`
    // name is not renamed, and the difference stays, with a hint
    let n = normalizer();
    let mut a = spec(&REF, true);
    let mut b = cand();
    a.http[4].body = b"{\"service\": \"maya\"}".to_vec();
    b.http[4].body = b"{\"service\": \"pulsar-console\"}".to_vec();
    let r = compare(
        &n.normalize(&build(&a), Side::Reference, &ctx(&REF))
            .unwrap_or_else(|e| panic!("{e}")),
        &n.normalize(&build(&b), Side::Candidate, &ctx(&CAND))
            .unwrap_or_else(|e| panic!("{e}")),
        &[],
        &approved(),
        Some(n.renames()),
    );
    let d = r
        .differences
        .iter()
        .find(|d| d.pointer == "/http/4/content/value/service");
    assert!(d
        .and_then(|d| d.hint.as_deref())
        .is_some_and(|h| h.contains("BRAND-1.6")));
}

// ------------------------------------------------------------------ Content-Length rule

#[test]
fn a_listed_content_length_is_derived_from_the_normalized_body_only() {
    let n = cl_normalizer();
    // a figure whose length differs between the sides: the normalized bodies agree, so
    // the derived lengths agree
    let mut c = cand();
    let ms = format!("\"prompt_ms\": {}", CAND.figs[0]);
    replace_body(&mut c, 0, &ms, "\"prompt_ms\": 123456.75");
    assert!(check_with(&n, &c, &[]).clean());
    // without the entry the lengths differ: the header shows the two lengths received
    let r = check_without_cl(&c);
    let d = r
        .differences
        .iter()
        .find(|d| d.pointer == "/http/0/head/headers/3/1");
    assert!(d.is_some_and(|d| d.reference != d.candidate));
    // a body that really differs still differs, in the header too
    let mut c = cand();
    replace_body(&mut c, 0, "\"Hi\"", "\"Hi!\"");
    let r = check_with(&n, &c, &[]);
    expect_diff_anywhere(&r, "/http/0/head/headers/3/1");
    expect_diff(&r, "/http/0/body/text");
}

// ------------------------------------------------------------------ review round 1

#[test]
fn log_figures_are_volatile_and_the_token_count_is_not() {
    // serve/server.py:4745: only the elapsed time and the rate of the done line
    let r = check(&cand(), &[]);
    assert!(!pointers(&r).iter().any(|p| p.starts_with("/log")));
    for (from, to) in [
        ("done: 1 tokens", "done: 2 tokens"),
        ("(7.0 tok/s)", "(7 tok/s)"),
        ("(7.0 tok/s)", "(fast tok/s)"),
        ("(stop, cancel=False)", "(length, cancel=False)"),
    ] {
        let mut c = cand();
        assert!(c.log[2].contains(from), "{from}");
        c.log[2] = c.log[2].replace(from, to);
        expect_diff(&check(&c, &[]), "/log/2");
    }
}

fn add_entry(s: &mut Spec, entry: &str) {
    replace_body(
        s,
        4,
        "\"service\": \"svc\"",
        &format!("\"service\": \"svc\", \"entry\": {entry}"),
    );
}

fn model_entry(tmp: &str, pre: &str) -> String {
    format!(
        "{{\"name\": \"{pre}-a:latest\", \"model\": \"{pre}-a:latest\", \"file\": \"{pre}-a.json\", \
         \"path\": \"{tmp}/models/{pre}-a.json\", \"folder\": \"{tmp}/models\", \"to\": \"{pre}-b.json\"}}"
    )
}

#[test]
fn decided_renames_and_temporary_paths_in_model_entries_compare_clean() {
    // serve/model_api.py:69 (name and model), 92 (file, folder), serve/models.py:758
    // (path) and serve/server.py:3159 (to)
    let mut a = spec(&REF, true);
    add_entry(&mut a, &model_entry(REF.tmp, "maya"));
    let mut b = cand();
    add_entry(&mut b, &model_entry(CAND.tmp, "pulsar"));
    let r = check_pair_with(&cl_normalizer(), &a, &b);
    assert!(
        r.clean(),
        "{}",
        serde_json::to_string_pretty(&r.to_json()).unwrap_or_default()
    );
    // a path outside the temporary directory, or a candidate that keeps a donor name
    let folder = format!("\"folder\": \"{}/models\"", CAND.tmp);
    for (from, to, at) in [
        (folder.as_str(), "\"folder\": \"/var/models\"", "folder"),
        (
            "\"name\": \"pulsar-a:latest\"",
            "\"name\": \"maya-a:latest\"",
            "name",
        ),
        (
            "\"file\": \"pulsar-a.json\"",
            "\"file\": \"maya-a.json\"",
            "file",
        ),
        ("\"to\": \"pulsar-b.json\"", "\"to\": \"maya-b.json\"", "to"),
    ] {
        let mut b = cand();
        add_entry(&mut b, &model_entry(CAND.tmp, "pulsar").replace(from, to));
        expect_diff(
            &check_pair_with(&cl_normalizer(), &a, &b),
            &format!("/http/4/content/value/entry/{at}"),
        );
    }
    // a name that does not repeat its object's model (a tool's name, say) is not renamed
    let mut a = spec(&REF, true);
    add_entry(&mut a, "{\"name\": \"maya-x\"}");
    let mut b = cand();
    add_entry(&mut b, "{\"name\": \"pulsar-x\"}");
    expect_diff(
        &check_pair_with(&cl_normalizer(), &a, &b),
        "/http/4/content/value/entry/name",
    );
}

#[test]
fn placeholder_text_in_a_picture_file_name_is_a_difference() {
    // the probe uses the prefix the id is numbered under (`<req-#`), not the extension
    let mut reference = spec(&REF, true);
    reference
        .files
        .push(("vision/req-0123456789ab.dsi".into(), "x".into()));
    let mut candidate = cand();
    candidate
        .files
        .push(("vision/<req-#1>.dsi".into(), "x".into()));
    let r = check_pair_with(&cl_normalizer(), &reference, &candidate);
    assert!(!r.passed(), "placeholder text in a file name was hidden");
    assert!(r
        .differences
        .iter()
        .any(|d| d.kind == DiffKind::Normalization(Side::Candidate)));
    // in a log line too
    let mut c = cand();
    c.log[0] = format!("{} <req-#1>", c.log[0]);
    let r = check(&c, &[]);
    assert!(r
        .differences
        .iter()
        .any(|d| d.kind == DiffKind::Normalization(Side::Candidate) && d.pointer == "/log/0"));
}

#[test]
fn a_client_supplied_id_replaced_by_a_fresh_one_is_a_difference() {
    // the request of exchange 0 carries CLIENT_ITEM on both sides; the donor echoes it
    let echo = |s: &mut Spec, id: &str| {
        replace_body(
            s,
            0,
            "\"object\": \"chat.completion\"",
            &format!("\"echo\": \"{id}\", \"object\": \"chat.completion\""),
        )
    };
    let mut reference = spec(&REF, true);
    echo(&mut reference, CLIENT_ITEM);
    let mut candidate = cand();
    echo(&mut candidate, "item_bbbbbbbbbbbbbbbbbbbbbbbb");
    let r = check_pair(&reference, &candidate);
    expect_diff(&r, "/http/0/content/value/echo");
    // echoing the client's own id compares clean
    let mut candidate = cand();
    echo(&mut candidate, CLIENT_ITEM);
    assert!(check_pair_with(&cl_normalizer(), &reference, &candidate).clean());
}

#[test]
fn files_are_numbered_in_an_order_that_does_not_depend_on_their_ids() {
    // two answers seen only in files, whose random ids sort the other way round on the
    // candidate side (serve/server.py:4936, 5140)
    let answer = |r: &Run, id: String, text: &str| {
        (
            format!("answers/chatcmpl-{id}.jsonl"),
            format!(
                "{{\"id\": \"chatcmpl-{id}\", \"created\": {}, \"content\": \"{text}\"}}\n",
                r.t + 9
            ),
        )
    };
    let mut a = spec(&REF, true);
    a.files.push(answer(&REF, "a".repeat(24), "A"));
    a.files.push(answer(&REF, "b".repeat(24), "B"));
    let mut b = cand();
    b.files.push(answer(&CAND, "f".repeat(24), "A"));
    b.files.push(answer(&CAND, "c".repeat(24), "B"));
    let r = check_pair_with(&cl_normalizer(), &a, &b);
    assert!(
        r.clean(),
        "{}",
        serde_json::to_string_pretty(&r.to_json()).unwrap_or_default()
    );
    // a content that really differs still does
    let last = b.files.len() - 1;
    b.files[last].1 = b.files[last].1.replace("\"B\"", "\"C\"");
    assert!(!check_pair_with(&cl_normalizer(), &a, &b).passed());
}

#[test]
fn bytes_after_a_complete_body_are_kept_after_a_half_close() {
    // after a half-close the client reads on: what the server sends past the body is
    // observable
    let half = json!({"trigger": "after-request", "mode": "half-close", "fired": true, "body_bytes": 0, "events": 0});
    let mut a = build(&spec(&REF, true));
    a["http"][0]["disconnect"] = half.clone();
    let s = cand();
    let mut b = build(&s);
    b["http"][0]["disconnect"] = half;
    let mut wire = exchange(&s.http[0]).wire;
    wire.extend_from_slice(b"HTTP/1.0 200 OK\r\n\r\nextra");
    b["http"][0]["wire"] = console_conformance::observe::bytes_json(&wire);
    let r = compare_documents(
        &cl_normalizer(),
        &a,
        &ctx(&REF),
        &b,
        &ctx(&CAND),
        &[],
        &approved(),
    )
    .unwrap_or_else(|e| panic!("{e}"));
    expect_diff(&r, "/http/0/wire");
}

#[test]
fn bytes_past_the_body_after_a_close_disconnect_are_client_timing() {
    let s = cand();
    let n = normalizer();
    let mut v = build(&s);
    let text = String::from_utf8(exchange(&s.http[1]).body).unwrap_or_default();
    let first = text.find("\n\n").map_or(0, |i| i + 2);
    v["http"][1]["body"] =
        console_conformance::observe::bytes_json(text.get(..first).unwrap_or_default().as_bytes());
    v["http"][1]["end"] = json!({"kind": "disconnected"});
    v["http"][1]["server_closed"] = Value::Null;
    v["http"][1]["disconnect"] = json!({"trigger": "after-events", "n": 1, "mode": "close", "fired": true, "body_bytes": first, "events": 1});
    let out = n
        .normalize(&v, Side::Candidate, &ctx(&CAND))
        .unwrap_or_else(|e| panic!("{e}"));
    assert_eq!(out.document["http"][1]["wire"], json!("consistent"));
    // the same bytes after a half-close are kept
    v["http"][1]["disconnect"]["mode"] = json!("half-close");
    let out = n
        .normalize(&v, Side::Candidate, &ctx(&CAND))
        .unwrap_or_else(|e| panic!("{e}"));
    assert_ne!(out.document["http"][1]["wire"], json!("consistent"));
}

#[test]
fn a_wildcard_annotation_cannot_suppress_unrelated_header_values() {
    let mut c = cand();
    c.http[0].headers[2].1 = "text/json".into();
    // (CNF-04F: it names its kind, so that the wildcard rule is the only reason left to
    // refuse it)
    let wide = Annotation::new("P-1", "/http/*/head/headers/*/1").covering(CoveredKind::Value);
    let r = check_cl(&c, &[wide]);
    expect_diff(&r, "/http/0/head/headers/2/1");
    assert!(r.suppressed.is_empty());
    assert!(matches!(
        &r.annotation_errors[0].problem,
        AnnotationProblem::Shape(s) if s.contains("wildcard pointer needs")
    ));
    // with the value it expects, it suppresses only a difference that shows it
    let scoped = Annotation::new("P-1", "/http/*/head/headers/*/1")
        .covering(CoveredKind::Value)
        .expecting(None, Some(json!("pulsar-console/0.1.0")));
    let r = check_cl(&c, &[scoped]);
    expect_diff(&r, "/http/0/head/headers/2/1");
    assert!(r.suppressed.is_empty() && r.annotation_errors.is_empty());
    assert_eq!(r.unused_annotations, [0]);
}

#[test]
fn a_figure_in_another_float_notation_is_a_difference() {
    // Python's repr writes 5e-05 below 1e-4
    let ms = |r: &Run| format!("\"prompt_ms\": {}", r.figs[0]);
    let mut a = spec(&REF, true);
    replace_body(&mut a, 0, &ms(&REF), "\"prompt_ms\": 5e-05");
    let mut b = cand();
    replace_body(&mut b, 0, &ms(&CAND), "\"prompt_ms\": 0.00005");
    expect_diff(
        &check_pair(&a, &b),
        "/http/0/content/value/timings/prompt_ms",
    );
    // the same notation is volatile
    let mut b = cand();
    replace_body(&mut b, 0, &ms(&CAND), "\"prompt_ms\": 7.5e-05");
    assert!(check_pair_with(&cl_normalizer(), &a, &b).clean());
}

#[test]
fn a_reference_stored_in_its_normalized_form_replays() {
    let n = cl_normalizer();
    let stored = n
        .normalize(&build(&spec(&REF, true)), Side::Reference, &ctx(&REF))
        .unwrap_or_else(|e| panic!("{e}"));
    let text = serde_json::to_string_pretty(&stored.document).unwrap_or_default();
    let read: Value = serde_json::from_str(&text).unwrap_or_else(|e| panic!("{e}"));
    let fresh = |c: &Spec| {
        n.normalize(&build(c), Side::Candidate, &ctx(&CAND))
            .unwrap_or_else(|e| panic!("{e}"))
    };
    // (CNF-04F: a stored reference is checked against the normalizer and the context
    // it was recorded with)
    let stored =
        |v: &Value| Normalized::stored(v.clone(), &n, &ctx(&REF)).unwrap_or_else(|e| panic!("{e}"));
    let r = compare(
        &stored(&read),
        &fresh(&cand()),
        &[],
        &approved(),
        Some(n.renames()),
    );
    assert!(
        r.clean(),
        "{}",
        serde_json::to_string_pretty(&r.to_json()).unwrap_or_default()
    );
    let mut c = cand();
    c.http[0].code = 201;
    let r = compare(
        &stored(&read),
        &fresh(&c),
        &[],
        &approved(),
        Some(n.renames()),
    );
    expect_diff(&r, "/http/0/head/code");
    // a stored document is not an observation: normalizing it again is refused
    assert!(n.normalize(&read, Side::Reference, &ctx(&REF)).is_err());
}
