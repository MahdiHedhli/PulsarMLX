//! Tests of the test kit's in-process server (work package API-19): the builder over the
//! transport, the router and the turn driver, a handler factory that streams an engine's
//! tokens as SSE, the SSE reader against it, the guards read from a run config, the
//! transport settings read from the injected environment and the run config's `env` block,
//! the configuration folder, and the synthetic-only refusal at start.
//!
//! These are tests of the kit itself, not re-expressions of donor methods.

use std::sync::Arc;

use console_core::config::RunConfig;
use console_core::engine::{GenerationRequest, RequestId};
use console_core::turn::{TurnItem, TurnRequest};
use console_http::guard::Refusal;
use console_http::router::{Route, RouteHandler, RouteRequest};
use console_http::transport::HandlerFuture;
use console_testkit::engines::{self, NotSyntheticEngine, CTX, HELLO};
use console_testkit::raw::{self, invalid_request, json_post, server_line, RawRequest};
use console_testkit::server::probe::RouteProbe;
use console_testkit::server::{Parts, StartError, TestServer};
use console_testkit::sse::{self, SseEnd};
use console_tokenizer::byte_tok::ByteTokenizer;
use serde_json::{json, Value};

/// A handler that runs one turn on the driver for `{"prompt": <text>, "max_tokens": <n>}`
/// and streams each token id as `data: {"id": <id>}`, then `data: [DONE]`.
struct TokenStream {
    parts: Parts,
}

impl RouteHandler for TokenStream {
    fn serve(&self, mut request: RouteRequest) -> HandlerFuture<'_> {
        Box::pin(async move {
            let body = request.body.clone().unwrap_or_default();
            let prompt = body.get("prompt").and_then(Value::as_str).unwrap_or("");
            let max_new = body
                .get("max_tokens")
                .and_then(Value::as_u64)
                .and_then(|n| u32::try_from(n).ok())
                .unwrap_or(1);
            let ids = self.parts.tokenizer.encode(prompt, true, &[]);
            let Some(driver) = &self.parts.driver else {
                let _ = request.exchange.responder().json(503, "{}").await;
                return;
            };
            let mut turn = driver.turn(TurnRequest::new(GenerationRequest::new(
                RequestId(0),
                ids,
                max_new,
            )));
            let Ok(mut sink) = request.exchange.responder().sse_start().await else {
                return;
            };
            while let Some(item) = turn.next().await {
                match item {
                    TurnItem::Token(t) => {
                        let frame = format!("data: {{\"id\": {}}}\n\n", t.id);
                        if sink.send(frame.as_bytes()).await.is_err() {
                            return;
                        }
                    }
                    TurnItem::Ping(_) => {
                        let _ = sink.send(b": keep-alive\n\n").await;
                    }
                    TurnItem::Done(_) => break,
                }
            }
            let _ = sink.send(b"data: [DONE]\n\n").await;
        })
    }
}

fn token_stream(parts: &Parts) -> Arc<dyn RouteHandler> {
    Arc::new(TokenStream {
        parts: parts.clone(),
    })
}

#[tokio::test]
async fn an_engine_streams_through_a_registered_handler() {
    let engine = engines::recording(HELLO).expect("valid script");
    let probe = engine.probe();
    let server = TestServer::builder()
        .engine(engines::shared(engine))
        .route_with(Route::ChatCompletions, token_stream)
        .start()
        .await
        .expect("starts");
    assert_eq!(
        server.driver().map(|d| d.max_context()),
        Some(CTX),
        "the driver reports the engine's context"
    );
    let body = br#"{"prompt": "hi", "max_tokens": 4}"#;
    let mut reader = server.sse(&json_post("/v1/chat/completions", body)).await;
    assert_eq!(reader.head().status, 200);
    // The `Server` value is the product's (approved deviation P-1).
    assert_eq!(
        reader.head().head,
        format!(
            "HTTP/1.0 200 OK\r\n{}\r\nDate: <date>\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache",
            server_line()
        )
    );
    let frames = reader.frames_until_done().await;
    let ids: Vec<u64> = sse::data_json(&frames)
        .iter()
        .filter_map(|j| j.get("id").and_then(Value::as_u64))
        .collect();
    let script = engines::script_ids(&ByteTokenizer::new(), HELLO);
    let want: Vec<u64> = script.iter().take(4).map(|&i| u64::from(i)).collect();
    assert_eq!(ids, want, "max_new cuts the script");
    let raw: Vec<u8> = frames.iter().flat_map(|f| f.raw.clone()).collect();
    assert_eq!(
        String::from_utf8_lossy(&raw),
        format!(
            "data: {{\"id\": {}}}\n\ndata: {{\"id\": {}}}\n\ndata: {{\"id\": {}}}\n\ndata: {{\"id\": {}}}\n\ndata: [DONE]\n\n",
            want[0], want[1], want[2], want[3]
        ),
        "the frames' raw bytes are the stream"
    );
    assert_eq!(
        reader.next_frame().await,
        Err(SseEnd::Closed { rest: Vec::new() }),
        "the connection closes after the stream"
    );
    // The donor's RecordingEngine.last_max_new, through the probe.
    let last = probe.last_request().expect("the engine saw the request");
    assert_eq!(last.max_new, 4);
    assert_eq!(probe.last_prompt(), Some(vec![104, 105]));
    let _ = server.stop().await;
}

#[tokio::test]
async fn a_whole_stream_reads_as_one_response_too() {
    let server = TestServer::builder()
        .engine(engines::shared(engines::recording("ab").expect("valid")))
        .route_with(Route::ChatCompletions, token_stream)
        .start()
        .await
        .expect("starts");
    let r = server
        .exchange(&json_post(
            "/v1/chat/completions",
            br#"{"prompt": "x", "max_tokens": 64}"#,
        ))
        .await;
    assert_eq!(r.status, 200);
    let frames = sse::frames_of(&r);
    assert_eq!(
        frames.len(),
        4,
        "a, b, the end-of-turn id and [DONE]: {frames:?}"
    );
    assert!(frames.last().is_some_and(sse::SseFrame::is_done));
    assert!(sse::parse_frames(&r.body).rest.is_empty());
}

#[tokio::test]
async fn the_guards_come_from_the_run_config_and_the_injected_key() {
    let mut cfg = RunConfig::new();
    cfg.set("api_key", json!("k1"));
    cfg.set("cors_origins", json!(["http://127.0.0.1:8090/"]));
    let server = TestServer::builder()
        .run_config(cfg.clone())
        .route(Route::ChatCompletions, Arc::new(RouteProbe))
        .start()
        .await
        .expect("starts");
    let chat = r#"{"model": "m"}"#;
    let r = server.post_json("/v1/chat/completions", &[], chat).await;
    assert_eq!(r.status, 401);
    assert_eq!(r.text(), Refusal::auth().body());
    let r = server
        .post_json(
            "/v1/chat/completions",
            &[("Authorization", "Bearer k1")],
            chat,
        )
        .await;
    assert_eq!(r.status, 200, "{}", r.text());
    assert_eq!(r.routed().as_deref(), Some("ChatCompletions"));
    assert_eq!(r.json()["body"], json!({"model": "m"}));
    let r = server
        .post_json(
            "/v1/chat/completions",
            &[
                ("Authorization", "Bearer k1"),
                ("Origin", "http://127.0.0.1:8090"),
            ],
            chat,
        )
        .await;
    assert_eq!(
        r.header("Access-Control-Allow-Origin"),
        Some("http://127.0.0.1:8090"),
        "the run config's origin, its trailing slash forgiven"
    );
    drop(server);

    // The injected PULSAR_CONSOLE_API_KEY wins over the run config's key, as at start.
    let server = TestServer::builder()
        .run_config(cfg)
        .env("PULSAR_CONSOLE_API_KEY", "envkey")
        .route(Route::ChatCompletions, Arc::new(RouteProbe))
        .start()
        .await
        .expect("starts");
    let r = server
        .post_json(
            "/v1/chat/completions",
            &[("Authorization", "Bearer k1")],
            chat,
        )
        .await;
    assert_eq!(r.status, 401);
    let r = server
        .post_json(
            "/v1/chat/completions",
            &[("Authorization", "Bearer envkey")],
            chat,
        )
        .await;
    assert_eq!(r.status, 200);
}

#[tokio::test]
async fn a_bad_run_config_value_stops_the_start() {
    let mut cfg = RunConfig::new();
    cfg.set("cors_origins", json!("http://a:1"));
    let err = TestServer::builder().run_config(cfg).start().await;
    assert!(matches!(err, Err(StartError::Config(_))), "{err:?}");
}

#[tokio::test]
async fn transport_settings_come_from_the_injected_environment() {
    let server = TestServer::builder()
        .env("PULSAR_CONSOLE_MAX_BODY_MIB", "1")
        .env("PULSAR_CONSOLE_HTTP_BACKLOG", "300")
        .start()
        .await
        .expect("starts");
    assert_eq!(server.parts().transport.max_body_bytes, 1 << 20);
    assert_eq!(server.backlog, 300);
    assert_eq!(
        server.parts().env_var("PULSAR_CONSOLE_HTTP_BACKLOG"),
        Some("300")
    );
    let r = server
        .exchange(&raw::donor_post(
            &format!("Content-Length: {}\r\n", 2u64 << 20),
            b"",
        ))
        .await;
    assert_eq!(r.status, 413);
    assert_eq!(
        r.text(),
        invalid_request(
            "the request body is larger than 1 MiB (PULSAR_CONSOLE_MAX_BODY_MIB raises the limit)"
        )
    );
    // Without the variable, the donor's default, whatever the shell running the test has.
    let plain = TestServer::builder().start().await.expect("starts");
    assert_eq!(plain.parts().transport.max_body_bytes, 256 << 20);
}

#[tokio::test]
async fn a_run_config_env_value_reaches_the_kit_servers_backlog() {
    // As at server start: the run config's `env` entry is laid over the injected
    // environment, and wins over it (follow-up API-08F).
    let mut cfg = RunConfig::new();
    cfg.set(
        "env",
        json!({"PULSAR_CONSOLE_HTTP_BACKLOG": "64", "PULSAR_CONSOLE_MAX_BODY_MIB": null}),
    );
    let server = TestServer::builder()
        .env("PULSAR_CONSOLE_HTTP_BACKLOG", "300")
        .env("PULSAR_CONSOLE_MAX_BODY_MIB", "2")
        .run_config(cfg)
        .start()
        .await
        .expect("starts");
    assert_eq!(server.backlog, 64);
    assert_eq!(server.parts().transport.backlog, 64);
    // A `null` entry is not applied: the injected value stays in force.
    assert_eq!(server.parts().transport.max_body_bytes, 2 << 20);
    // The injected environment itself is kept as given.
    assert_eq!(
        server.parts().env_var("PULSAR_CONSOLE_HTTP_BACKLOG"),
        Some("300")
    );
    // A transport configuration given whole still wins over both.
    let mut cfg = RunConfig::new();
    cfg.set("env", json!({"PULSAR_CONSOLE_HTTP_BACKLOG": "64"}));
    let given = TestServer::builder()
        .run_config(cfg)
        .transport(console_http::transport::TransportConfig {
            backlog: 7,
            ..console_http::transport::TransportConfig::default()
        })
        .start()
        .await
        .expect("starts");
    assert_eq!(given.backlog, 7);
}

#[tokio::test]
async fn a_temporary_config_folder_lives_as_long_as_the_server() {
    let server = TestServer::builder()
        .temp_config_dir()
        .start()
        .await
        .expect("starts");
    let dir = server.config_dir().expect("a folder").to_path_buf();
    assert!(dir.is_dir());
    std::fs::write(dir.join("pulsar-x.json"), b"{}").expect("write");
    drop(server);
    assert!(!dir.exists(), "removed with the server");
}

#[tokio::test]
async fn an_engine_that_is_not_synthetic_is_refused_at_start() {
    let engine = NotSyntheticEngine::declaring("real");
    let calls = engine.clone();
    let err = TestServer::builder()
        .engine(engines::shared(engine))
        .start()
        .await;
    let Err(StartError::Engine(failure)) = err else {
        panic!("the start should fail with the guard's refusal: {err:?}");
    };
    let text = failure.to_string();
    assert!(
        text.contains(console_core::engine::ALLOWING_NON_SYNTHETIC_ENGINES_PATH),
        "{text}"
    );
    assert_eq!(
        calls.generate_calls(),
        0,
        "the refused engine served nothing"
    );
}

#[tokio::test]
async fn a_raw_handler_takes_no_router_settings() {
    let router_and_handler = TestServer::builder()
        .handler(Arc::new(NoAnswer))
        .api_key(json!("k"))
        .start()
        .await;
    assert!(matches!(router_and_handler, Err(StartError::Conflict(_))));
    let loopback = || console_http::guard::GuardConfig::new(console_testkit::server::LOOPBACK);
    let probed = console_testkit::server::probe::probed;
    // A given router keeps its own guards: a separate setting would be silently dropped.
    let router_and_key = TestServer::builder()
        .router(probed(loopback()))
        .api_key(json!("k"))
        .start()
        .await;
    assert!(matches!(router_and_key, Err(StartError::Conflict(_))));
    let router_and_guard = TestServer::builder()
        .router(probed(loopback()))
        .guard(loopback())
        .start()
        .await;
    assert!(matches!(router_and_guard, Err(StartError::Conflict(_))));
    let router_and_config = TestServer::builder()
        .router(probed(loopback()))
        .run_config(RunConfig::new())
        .start()
        .await;
    assert!(matches!(router_and_config, Err(StartError::Conflict(_))));
    // A whole guard config takes no separate guard settings either.
    for builder in [
        TestServer::builder().guard(loopback()).api_key(json!("k")),
        TestServer::builder()
            .guard(loopback())
            .cors_origins(vec!["http://a:1".to_owned()]),
        TestServer::builder().guard(loopback()).allowed_hosts(None),
        TestServer::builder()
            .guard(loopback())
            .run_config(RunConfig::new()),
    ] {
        let started = builder.start().await;
        assert!(
            matches!(started, Err(StartError::Conflict(_))),
            "{started:?}"
        );
    }
    let guard_alone = TestServer::builder()
        .guard(loopback())
        .route(Route::Health, Arc::new(RouteProbe))
        .start()
        .await
        .expect("starts");
    assert_eq!(
        guard_alone.get("/health", &[]).await.routed().as_deref(),
        Some("Health")
    );
    let only_handler = TestServer::builder()
        .handler(Arc::new(NoAnswer))
        .start()
        .await
        .expect("starts");
    assert!(only_handler.router().is_none());
    let r = only_handler.send(RawRequest::get("/")).await;
    assert!(
        r.raw.is_empty(),
        "the handler wrote nothing, so nothing was sent"
    );
}

struct NoAnswer;

impl console_http::transport::Handler for NoAnswer {
    fn handle(&self, _exchange: console_http::transport::Exchange) -> HandlerFuture<'_> {
        Box::pin(async {})
    }
}

#[tokio::test]
async fn requests_get_the_servers_host_unless_they_name_one() {
    let server = TestServer::with_router(console_testkit::server::probe::probed(
        console_http::guard::GuardConfig::new(console_testkit::server::LOOPBACK),
    ))
    .await;
    assert_eq!(server.host(), format!("127.0.0.1:{}", server.port()));
    assert_eq!(
        server.base_url(),
        format!("http://127.0.0.1:{}", server.port())
    );
    let r = server.send(RawRequest::get("/health")).await;
    assert_eq!(r.routed().as_deref(), Some("Health"));
    let r = server
        .send(RawRequest::get("/health").header("Host", "evil.example"))
        .await;
    assert_eq!(r.status, 403, "the named Host is sent as it is");
    let r = server.get("/v1/models", &[]).await;
    assert_eq!(r.routed().as_deref(), Some("Models"));
}

/// Answers every request with a redirect: `/a` to `/b` by path, `/b` to `/c` by the full
/// base URL, `/c` with 200, `/loop` to itself, `/away` to another host.
struct Redirects {
    base: std::sync::Mutex<String>,
}

impl console_http::transport::Handler for Redirects {
    fn handle(&self, mut exchange: console_http::transport::Exchange) -> HandlerFuture<'_> {
        Box::pin(async move {
            let path = exchange.head().path().to_owned();
            let base = self.base.lock().map(|b| b.clone()).unwrap_or_default();
            let r = exchange.responder();
            let _ = match path.as_str() {
                "/a" => r.redirect("/b").await,
                "/b" => r.redirect(&format!("{base}/c")).await,
                "/c" => r.json(200, "{\"page\": true}").await,
                "/loop" => r.redirect("/loop").await,
                _ => r.redirect("http://elsewhere.example/").await,
            };
        })
    }
}

#[tokio::test]
async fn get_following_follows_redirects_on_the_same_server_as_urllib() {
    let handler = Arc::new(Redirects {
        base: std::sync::Mutex::new(String::new()),
    });
    let server = TestServer::builder()
        .handler(handler.clone())
        .start()
        .await
        .expect("starts");
    if let Ok(mut b) = handler.base.lock() {
        *b = server.base_url();
    }
    let plain = server.get("/a", &[]).await;
    assert_eq!(plain.status, 302, "get returns a redirect as it is");
    assert_eq!(plain.header("Location"), Some("/b"));
    let followed = server.get_following("/a", &[]).await;
    assert_eq!(followed.status, 200);
    assert_eq!(followed.json(), json!({"page": true}));
    let away = server.get_following("/away", &[]).await;
    assert_eq!(
        away.status, 302,
        "a redirect to another host is not followed"
    );
    let looping = server.get("/loop", &[]).await;
    assert_eq!(looping.status, 302);
}

#[tokio::test]
#[should_panic(expected = "more than 10 redirects")]
async fn get_following_stops_after_urllibs_ten_redirects() {
    let server = TestServer::builder()
        .handler(Arc::new(Redirects {
            base: std::sync::Mutex::new(String::new()),
        }))
        .start()
        .await
        .expect("starts");
    let _ = server.get_following("/loop", &[]).await;
}
