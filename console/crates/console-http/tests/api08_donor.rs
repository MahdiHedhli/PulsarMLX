//! Donor tests of work package API-08, re-expressed against the OpenAI Chat Completions
//! dialect on the inference driver, the router and the transport.
//!
//! Provenance: translated from project-maya serve/test_server.py::UsageAndStatus, serve/test_server.py::RequestBodies, serve/test_server.py::CorsOptIn::test_another_page_cannot_post_without_a_preflight, serve/test_server.py::PromptProgressStream and serve/test_logprobs.py::Api at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! The donor's servers render prompts with its chat template; in M1 the prompt is the
//! synthetic stand-in of lead decision LD45, and there is no reasoning parser, so a
//! script's `</think>` is answer text here. The methods below assert nothing that depends
//! on either: the donor methods that do (reasoning entries, tool calls, JSON mode after a
//! reasoning block, prompt token counts) stay pending for the packages of M2.

#[path = "api08_kit.rs"]
mod kit;

use std::sync::Arc;
use std::time::Instant;

use console_core::engine::{
    ControlProbe, EngineDescriptor, EngineFactory, EngineFailure, EngineInstance, EngineKind,
    EngineStartConfig, EventSink, GenerationRequest, ShutdownOutcome, Terminal,
};
use console_engine::fake::doubles::{ClockedEngine, LpEngine, PacedEngine, CLOCKED_REUSED};
use console_http::guard::GuardConfig;
use console_testkit::engines::{recording, script, shared, CTX, HELLO, LP_ANSWER};
use console_testkit::raw::donor_post;
use console_testkit::server::{TestServer, LOOPBACK};
use console_testkit::sse::{data_json, frames_of};
use kit::*;
use serde_json::{json, Value};

/// The donor's `RequestBodies.MSG`.
const MSG: &str = "{\"model\": \"m\", \"messages\": [{\"role\": \"user\", \"content\": \"hi\"}]}";

fn body_json(r: &console_testkit::raw::RawResponse) -> Value {
    console_pyjson::loads::loads_bytes(&r.body).unwrap_or(Value::Null)
}

/// The data chunks of a stream (the donor reads `line[6:]` of every `data: {` line).
fn chunks(r: &console_testkit::raw::RawResponse) -> Vec<Value> {
    data_json(&frames_of(r))
}

// ------------------------------------------------------------------------ UsageAndStatus

async fn clocked_server() -> TestServer {
    match ClockedEngine::new(script(HELLO, CTX)) {
        Ok(f) => server(shared(f)).await,
        Err(e) => panic!("{e}"),
    }
}

// Donor: serve/test_server.py::UsageAndStatus::test_openai
#[tokio::test]
async fn usage_and_status_openai() {
    let s = clocked_server().await;
    let r = post(&s, &chat("\"max_tokens\": 20, \"stream\": false")).await;
    assert_eq!(r.status, 200);
    let b = body_json(&r);
    let (u, t) = (&b["usage"], &b["timings"]);
    assert_eq!(b["model"], json!(MODEL));
    assert_eq!(
        u["prompt_tokens_details"]["cached_tokens"],
        json!(CLOCKED_REUSED)
    );
    assert_eq!(t["cache_n"], json!(CLOCKED_REUSED));
    let n = |v: &Value| v.as_f64().unwrap_or(f64::NAN);
    assert_eq!(n(&t["prompt_n"]) + n(&t["cache_n"]), n(&u["prompt_tokens"]));
    assert_eq!(n(&t["predicted_n"]), n(&u["completion_tokens"]));
    assert!((n(&t["prompt_per_second"]) - n(&t["prompt_n"]) / 0.040).abs() <= 0.1);
    // 20 ms a token.
    assert!((n(&t["predicted_per_second"]) - 50.0).abs() <= 0.1);
}

// Donor: serve/test_server.py::UsageAndStatus::test_openai_stream
#[tokio::test]
async fn usage_and_status_openai_stream() {
    let s = clocked_server().await;
    let r = post(&s, &chat("\"max_tokens\": 20, \"stream\": true")).await;
    assert_eq!(r.status, 200);
    let all = chunks(&r);
    let Some(last) = all.last() else {
        panic!("no chunk: {:?}", String::from_utf8_lossy(&r.raw));
    };
    assert_eq!(
        last["usage"]["prompt_tokens_details"]["cached_tokens"],
        json!(CLOCKED_REUSED)
    );
    assert_eq!(last["timings"]["cache_n"], json!(CLOCKED_REUSED));
    assert!(all.iter().all(|c| c["model"] == json!(MODEL)));
}

// ------------------------------------------------------------------------- RequestBodies

async fn hello_server() -> TestServer {
    match recording(HELLO) {
        Ok(f) => server(shared(f)).await,
        Err(e) => panic!("{e}"),
    }
}

// Donor: serve/test_server.py::RequestBodies::test_a_chunked_body
// Completes the row with API-02's console-http::api02_donor::a_chunked_body_is_decoded_for_the_handler
// (the transport half).
#[tokio::test]
async fn request_bodies_a_chunked_body() {
    let s = hello_server().await;
    let mut body = format!("{:x}\r\n{MSG}\r\n0\r\n\r\n", MSG.len()).into_bytes();
    let r = s
        .exchange(&donor_post("Transfer-Encoding: chunked\r\n", &body))
        .await;
    assert_eq!(r.status, 200, "{}", r.text());
    let dumped = console_pyjson::dumps::to_python_default(&body_json(&r)).unwrap_or_default();
    assert!(dumped.contains("hello"), "{dumped}");
    body = b"zz\r\nab\r\n0\r\n\r\n".to_vec();
    let r = s
        .exchange(&donor_post("Transfer-Encoding: chunked\r\n", &body))
        .await;
    assert_eq!(r.status, 400);
}

// Donor: serve/test_server.py::RequestBodies::test_a_malformed_body_is_a_400
// Completes the row with API-02's
// console-http::api02_donor::a_malformed_body_reaches_the_handler_intact (the bodies reach
// the handler intact); the `[]` answer is the router's (API-03).
#[tokio::test]
async fn request_bodies_a_malformed_body_is_a_400() {
    let s = hello_server().await;
    let r = s
        .exchange(&donor_post("Content-Length: 2\r\n", b"[]"))
        .await;
    assert_eq!(r.status, 400);
    let bad = r#"{"model": "m", "messages": [{"role": "user", "content": {"no": "list"}}, 7]}"#;
    let r = s
        .exchange(&donor_post(
            &format!("Content-Length: {}\r\n", bad.len()),
            bad.as_bytes(),
        ))
        .await;
    assert_eq!(r.status, 400, "{}", r.text());
    // The donor's AttributeError, answered as a malformed request (approved deviation P-3).
    assert_eq!(
        body_json(&r)["error"]["message"],
        json!("malformed request (AttributeError: 'int' object has no attribute 'get')")
    );
}

// Donor: serve/test_server.py::RequestBodies::test_several_api_keys
// Completes the row with API-03's console-http::api03_donor::several_api_keys (the key
// parsing and the 401 answers).
#[tokio::test]
async fn request_bodies_several_api_keys() {
    let s = hello_server().await;
    let Some(router) = s.router().cloned() else {
        panic!("the test server has a router");
    };
    let send = |key: &str| {
        donor_post(
            &format!(
                "Authorization: Bearer {key}\r\nContent-Length: {}\r\n",
                MSG.len()
            ),
            MSG.as_bytes(),
        )
    };
    router.replace_guard(GuardConfig::new(LOOPBACK).with_api_key(&json!("k1, k2")));
    for (key, want) in [("k1", 200), ("k2", 200), ("k3", 401), ("k1, k2", 401)] {
        let r = s.exchange(&send(key)).await;
        assert_eq!(r.status, want, "{key}");
    }
    // A list in the config: a key with a comma in it.
    router.replace_guard(GuardConfig::new(LOOPBACK).with_api_key(&json!(["a,b"])));
    let r = s.exchange(&send("a,b")).await;
    assert_eq!(r.status, 200);
}

// ------------------------------------------------------------------------------ CorsOptIn

// Donor: serve/test_server.py::CorsOptIn::test_another_page_cannot_post_without_a_preflight
// Completes the row with API-03's
// console-http::api03_donor::cors_another_page_cannot_post_without_a_preflight (the 403
// refusals).
#[tokio::test]
async fn cors_another_page_cannot_post_without_a_preflight() {
    let s = hello_server().await;
    for origin in ["http://evil.example", "null"] {
        let r = s
            .call(
                "POST",
                "/v1/chat/completions",
                &[("Content-Type", "text/plain"), ("Origin", origin)],
                Some(MSG.as_bytes()),
            )
            .await;
        assert_eq!(r.status, 403, "{origin}");
    }
    // curl and the SDKs send no Origin.
    let r = post(&s, MSG).await;
    assert_eq!(r.status, 200);
    let r = s
        .call(
            "DELETE",
            "/v1/responses/resp_x",
            &[("Origin", "http://evil.example")],
            None,
        )
        .await;
    assert_eq!(r.status, 403);
}

// ------------------------------------------------------------------- PromptProgressStream

async fn paced_server() -> TestServer {
    match PacedEngine::new(script(HELLO, CTX)) {
        Ok(f) => server(shared(f)).await,
        Err(e) => panic!("{e}"),
    }
}

// Donor: serve/test_server.py::PromptProgressStream::test_asked_for_and_sent
// Completes the row with ENG-10's
// console-core::eng10_turn::prompt_progress_becomes_pings_with_its_payload (the ping
// payload) and ENG-02's PacedEngine.
#[tokio::test]
async fn prompt_progress_stream_asked_for_and_sent() {
    let s = paced_server().await;
    let body = chat("\"stream\": true, \"return_progress\": true, \"max_tokens\": 20");
    let r = post(&s, &body).await;
    let pps: Vec<Value> = chunks(&r)
        .into_iter()
        .filter_map(|c| c.get("prompt_progress").cloned())
        .collect();
    assert_eq!(
        pps,
        vec![
            json!({"total": 8192, "cache": 2048, "processed": 4096, "time_ms": 251}),
            json!({"total": 8192, "cache": 2048, "processed": 8192, "time_ms": 500}),
        ]
    );
    let r = post(&s, &body).await;
    assert!(chunks(&r).iter().any(|c| {
        let d = &c["choices"][0]["delta"];
        d.get("content").is_some() || d.get("reasoning_content").is_some()
    }));
}

// Donor: serve/test_server.py::PromptProgressStream::test_not_asked_for_is_not_sent
#[tokio::test]
async fn prompt_progress_stream_not_asked_for_is_not_sent() {
    // Stronger than the donor's plain engine: the engine does report progress here.
    let s = paced_server().await;
    let r = post(&s, &chat("\"stream\": true, \"max_tokens\": 20")).await;
    let all = chunks(&r);
    assert!(!all.is_empty());
    assert!(!all.iter().any(|c| c.get("prompt_progress").is_some()));
}

// Donor: serve/test_server.py::PromptProgressStream::test_non_stream_is_untouched
#[tokio::test]
async fn prompt_progress_stream_non_stream_is_untouched() {
    let s = paced_server().await;
    let r = post(&s, &chat("\"return_progress\": true, \"max_tokens\": 20")).await;
    assert_eq!(r.status, 200);
    let out = body_json(&r);
    assert!(out.get("prompt_progress").is_none());
    assert!(out.get("usage").is_some());
}

// ------------------------------------------------------------------------ test_logprobs

/// The donor's `Http` set-up: LpEngine's answer `abc</think>Hello`, context 8192.
fn lp_engine() -> LpEngine {
    match LpEngine::new(script(LP_ANSWER, 8192)) {
        Ok(f) => f,
        Err(e) => panic!("{e}"),
    }
}

/// The donor's `Http.chat`: model, `max_tokens` 64, one user message.
fn lp_chat(extra: &str) -> String {
    let sep = if extra.is_empty() { "" } else { ", " };
    format!("{{\"model\": \"m\", \"max_tokens\": 64, \"messages\": [{{\"role\": \"user\", \"content\": \"hi\"}}]{sep}{extra}}}")
}

// Donor: serve/test_logprobs.py::Api::test_not_asked
#[tokio::test]
async fn api_not_asked() {
    let engine = lp_engine();
    let probe = engine.probe();
    let s = server(shared(engine)).await;
    let r = post(&s, &lp_chat("")).await;
    let out = body_json(&r);
    assert!(out["choices"][0].get("logprobs").is_none());
    let asked = probe.last_request().map(|g| g.logprobs);
    assert_eq!(asked, Some(None), "the engine was asked for no logprobs");
    let r = post(&s, &lp_chat("\"stream\": true, \"logprobs\": false")).await;
    let all = chunks(&r);
    assert!(!all.is_empty());
    assert!(!all
        .iter()
        .any(|c| c["choices"][0].get("logprobs").is_some()));
}

/// An engine that does not report logprobs (`INFO logprobs=` absent): the scripted
/// engine with that capability taken out of its descriptor.
struct NoLogprobs(LpEngine);

struct NoLogprobsInstance {
    inner: Box<dyn EngineInstance>,
    desc: EngineDescriptor,
}

impl EngineFactory for NoLogprobs {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let inner = self.0.start(cfg)?;
        let mut desc = inner.descriptor().clone();
        desc.caps.logprobs_max = None;
        Ok(Box::new(NoLogprobsInstance { inner, desc }))
    }
}

impl EngineInstance for NoLogprobsInstance {
    fn descriptor(&self) -> &EngineDescriptor {
        &self.desc
    }

    fn generate(
        &mut self,
        req: &GenerationRequest,
        control: &ControlProbe,
        sink: &mut dyn EventSink,
    ) -> Result<Terminal, EngineFailure> {
        self.inner.generate(req, control, sink)
    }

    fn shutdown(self: Box<Self>, deadline: Instant) -> ShutdownOutcome {
        self.inner.shutdown(deadline)
    }
}

// Donor: serve/test_logprobs.py::Api::test_refused
#[tokio::test]
async fn api_refused() {
    let s = server(shared(lp_engine())).await;
    let r = post(&s, &lp_chat("\"top_logprobs\": 2")).await;
    assert_eq!(r.status, 400);
    let message = body_json(&r)["error"]["message"].clone();
    assert!(
        message.as_str().unwrap_or("").contains("top_logprobs"),
        "{message}"
    );
    let r = post(&s, &lp_chat("\"logprobs\": true, \"top_logprobs\": 30")).await;
    assert_eq!(r.status, 400);
    // An engine that does not say INFO logprobs=: a 400, not an answer without them.
    let s = server(Arc::new(NoLogprobs(lp_engine()))).await;
    let r = post(&s, &lp_chat("\"logprobs\": true")).await;
    assert_eq!(r.status, 400);
    let message = body_json(&r)["error"]["message"].clone();
    assert!(
        message.as_str().unwrap_or("").contains("log-probabilities"),
        "{message}"
    );
    // Not asked: served as ever.
    let r = post(&s, &lp_chat("")).await;
    assert_eq!(r.status, 200);
}
