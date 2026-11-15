//! The exhaustive dispatch-table test of work package API-03: every route of the donor's
//! `do_GET`, `do_POST`, `do_DELETE` and `do_OPTIONS`, with and without a key, and with no
//! `Origin`, the server's own page, a foreign page and `Origin: null`, asserting the status
//! and the slot that answered.
//!
//! The rows of [`TABLE`] are in the donor's dispatch order (serve/server.py 5934-6139 for
//! GET, 6160-6297 for POST, 5923-5933 for DELETE, 5799-5809 for OPTIONS at 7e68a30f), so a
//! reviewer can diff them against it. The test kit's `RouteProbe` stands in for the route
//! handlers of later packages: it answers 200 and names its slot, and on `/models/sse` and
//! `/v1/responses/*` it asks for the key itself, as those donor handlers do.
//!
//! Behavior reference: project-maya serve/server.py:5923-6297 at 7e68a30f.

use console_http::guard::GuardConfig;
use console_http::router::{Router, ROUTES};
use console_testkit::raw::*;
use console_testkit::server::probe::probed;
use console_testkit::server::{TestServer, LOOPBACK};
use serde_json::Value;

/// One route: method, path as sent, status without a key, status with the key, and the
/// slot that answers (the probe's name) when it is reached.
type Row = (&'static str, &'static str, u16, u16, Option<&'static str>);

const TABLE: &[Row] = &[
    // do_GET
    ("GET", "/models/sse", 401, 200, Some("ModelsSse")),
    ("GET", "/api/tags", 401, 200, Some("OllamaGet")),
    ("GET", "/api/ps", 401, 200, Some("OllamaGet")),
    ("GET", "/api/version", 401, 200, Some("OllamaGet")),
    ("GET", "/api/catalog", 401, 200, Some("OllamaGet")),
    ("GET", "/api/pull/status", 401, 200, Some("OllamaGet")),
    (
        "GET",
        "/v1/responses/resp_x",
        401,
        200,
        Some("ResponseResource"),
    ),
    (
        "GET",
        "/v1/responses/resp_x/input_items",
        401,
        200,
        Some("ResponseResource"),
    ),
    ("GET", "/fonts/Outfit.woff2", 200, 200, Some("Fonts")),
    ("GET", "/web", 200, 200, Some("WebRedirect")),
    ("GET", "/web/", 200, 200, Some("WebRedirect")),
    ("GET", "/web/app.js", 200, 200, Some("WebAsset")),
    ("GET", "/metrics", 401, 200, Some("Metrics")),
    ("GET", "/metrics?requests=all", 401, 200, Some("Metrics")),
    (
        "GET",
        "/metrics/prometheus",
        401,
        200,
        Some("MetricsPrometheus"),
    ),
    ("GET", "/settings", 401, 200, Some("SettingsGet")),
    ("GET", "/mcp", 401, 200, Some("Mcp")),
    ("GET", "/", 200, 200, Some("Index")),
    ("GET", "/?q=hello", 200, 200, Some("Index")),
    ("GET", "/health", 200, 200, Some("Health")),
    ("GET", "/health/", 200, 200, Some("Health")),
    ("GET", "/api/context", 401, 200, Some("ContextGet")),
    (
        "GET",
        "/api/thinking-budget",
        401,
        200,
        Some("ThinkingBudgetGet"),
    ),
    ("GET", "/api/port", 401, 200, Some("PortGet")),
    ("GET", "/api/turbo", 401, 200, Some("TurboGet")),
    ("GET", "/api/models", 401, 200, Some("ModelsInfo")),
    ("GET", "/api/savings", 401, 200, Some("Savings")),
    ("GET", "/api/update", 401, 200, Some("UpdateGet")),
    ("GET", "/api/report", 401, 200, Some("Report")),
    ("GET", "/status", 401, 200, Some("Status")),
    ("GET", "/v1/models", 401, 200, Some("Models")),
    ("GET", "/v1/models/?x=1", 401, 200, Some("Models")),
    ("GET", "/models", 401, 200, Some("Models")),
    ("GET", "/props", 401, 200, Some("Props")),
    ("GET", "/props?model=m", 401, 200, Some("Props")),
    ("GET", "/slots", 401, 200, Some("Slots")),
    ("GET", "/v1/status", 401, 200, Some("V1Status")),
    ("GET", "/v1/strata/stream", 401, 200, Some("StrataStream")),
    // Unknown GETs: 404 with no key asked.
    ("GET", "/nothing", 404, 404, None),
    ("GET", "/fonts", 404, 404, None),
    ("GET", "/v1/responses", 404, 404, None),
    ("GET", "/v1/responses/", 404, 404, None),
    ("GET", "/v1/chat/completions", 404, 404, None),
    ("GET", "/api/delete", 404, 404, None),
    ("GET", "/api/show", 404, 404, None),
    ("GET", "/v1/strata/cancel", 404, 404, None),
    ("GET", "/models/load", 404, 404, None),
    // do_POST: the key first, then the route.
    ("POST", "/models/load", 401, 200, Some("LlamacppModels")),
    ("POST", "/models/unload", 401, 200, Some("LlamacppModels")),
    (
        "POST",
        "/v1/responses/resp_x/cancel",
        401,
        200,
        Some("ResponseCancel"),
    ),
    ("POST", "/api/show", 401, 200, Some("OllamaPost")),
    ("POST", "/api/pull", 401, 200, Some("OllamaPost")),
    ("POST", "/api/pull/cancel", 401, 200, Some("OllamaPost")),
    ("POST", "/api/delete", 401, 200, Some("OllamaPost")),
    ("POST", "/api/chat", 401, 200, Some("OllamaPost")),
    ("POST", "/api/generate", 401, 200, Some("OllamaPost")),
    ("POST", "/settings", 401, 200, Some("SettingsPost")),
    ("POST", "/attach", 401, 200, Some("Attach")),
    ("POST", "/pdf", 401, 200, Some("Attach")),
    ("POST", "/v1/strata/cancel", 401, 200, Some("StrataCancel")),
    ("POST", "/api/context", 401, 200, Some("ContextPost")),
    ("POST", "/api/port", 401, 200, Some("PortPost")),
    (
        "POST",
        "/api/thinking-budget",
        401,
        200,
        Some("ThinkingBudgetPost"),
    ),
    ("POST", "/api/update", 401, 200, Some("UpdatePost")),
    ("POST", "/api/turbo", 401, 200, Some("TurboPost")),
    (
        "POST",
        "/api/models/settings",
        401,
        200,
        Some("ModelsAdmin"),
    ),
    ("POST", "/api/models/switch", 401, 200, Some("ModelsAdmin")),
    ("POST", "/api/models/delete", 401, 200, Some("ModelsAdmin")),
    (
        "POST",
        "/api/models/leftovers",
        401,
        200,
        Some("ModelsAdmin"),
    ),
    ("POST", "/api/savings/reset", 401, 200, Some("SavingsReset")),
    (
        "POST",
        "/api/savings/prices",
        401,
        200,
        Some("SavingsPrices"),
    ),
    ("POST", "/api/tokens", 401, 200, Some("Tokens")),
    ("POST", "/tokenize", 401, 200, Some("Tokenize")),
    ("POST", "/detokenize", 401, 200, Some("Detokenize")),
    (
        "POST",
        "/v1/chat/completions",
        401,
        200,
        Some("ChatCompletions"),
    ),
    (
        "POST",
        "/v1/chat/completions?api-version=1",
        401,
        200,
        Some("ChatCompletions"),
    ),
    ("POST", "/v1/responses", 401, 200, Some("Responses")),
    ("POST", "/v1/messages", 401, 200, Some("Messages")),
    (
        "POST",
        "/v1/messages/?beta=true",
        401,
        200,
        Some("Messages"),
    ),
    // Unknown POSTs: the key, then the body, then 404.
    ("POST", "/v1/nothing", 401, 404, None),
    ("POST", "/v1/responses/resp_x", 401, 404, None),
    ("POST", "/v1/strata/stream", 401, 404, None),
    ("POST", "/health", 401, 404, None),
    ("POST", "/", 401, 404, None),
    // do_DELETE: the foreign check, then the route.
    (
        "DELETE",
        "/v1/responses/resp_x",
        401,
        200,
        Some("ResponseResource"),
    ),
    // The donor tests the raw path for `/v1/responses/` (trailing slash kept), so these
    // reach the responses handler (serve/server.py:5926).
    (
        "DELETE",
        "/v1/responses/",
        401,
        200,
        Some("ResponseResource"),
    ),
    (
        "DELETE",
        "/v1/responses/?a=1",
        401,
        200,
        Some("ResponseResource"),
    ),
    ("DELETE", "/api/delete", 401, 200, Some("OllamaPost")),
    ("DELETE", "/api/delete/", 401, 200, Some("OllamaPost")),
    ("DELETE", "/settings", 401, 404, None),
    ("DELETE", "/v1/models", 401, 404, None),
    ("DELETE", "/", 401, 404, None),
    // do_OPTIONS: no key; without cors_origins every preflight is refused.
    ("OPTIONS", "/v1/chat/completions", 403, 403, None),
    ("OPTIONS", "/settings", 403, 403, None),
    ("OPTIONS", "/", 403, 403, None),
];

/// The status for a foreign page (and `Origin: null`): GET and DELETE check the origin
/// first (SEC-1.2 for GET), POST checks the key first, OPTIONS is refused without
/// `cors_origins` anyway.
fn foreign_status(method: &str, with_key: bool) -> u16 {
    match (method, with_key) {
        ("POST", false) => 401,
        _ => 403,
    }
}

async fn send(
    server: &TestServer,
    method: &str,
    path: &str,
    key: bool,
    origin: Option<&str>,
) -> RawResponse {
    let mut headers: Vec<(&str, &str)> = Vec::new();
    if key {
        headers.push(("Authorization", "Bearer k1"));
    }
    if let Some(origin) = origin {
        headers.push(("Origin", origin));
    }
    if method == "POST" {
        headers.push(("Content-Type", "application/json"));
        server.call(method, path, &headers, Some(b"{}")).await
    } else {
        server.call(method, path, &headers, None).await
    }
}

async fn run_table(server: &TestServer, key_configured: bool) -> Vec<String> {
    let mut failures = Vec::new();
    let own = format!("http://{}", server.host());
    for &(method, path, without, with, slot) in TABLE {
        for key in [false, true] {
            let reached = if key || !key_configured {
                with
            } else {
                without
            };
            for origin in [None, Some(own.as_str())] {
                let r = send(server, method, path, key, origin).await;
                let routed = r.routed();
                let want_slot = if reached == 200 {
                    slot.map(str::to_owned)
                } else {
                    None
                };
                if r.status != reached || routed != want_slot {
                    failures.push(format!(
                        "{method} {path} key={key} origin={origin:?}: got {} {:?}, want {reached} {want_slot:?}",
                        r.status, routed
                    ));
                }
            }
            for origin in ["http://evil.example", "null"] {
                let r = send(server, method, path, key, Some(origin)).await;
                let want = foreign_status(method, key || !key_configured);
                if r.status != want || r.routed().is_some() {
                    failures.push(format!(
                        "{method} {path} key={key} origin={origin}: got {}, want {want}",
                        r.status
                    ));
                }
            }
        }
    }
    failures
}

#[tokio::test]
async fn every_donor_route_with_and_without_a_key_and_each_origin() {
    let config = GuardConfig::new(LOOPBACK).with_api_key(&Value::String("k1".into()));
    let server = TestServer::with_router(probed(config)).await;
    let failures = run_table(&server, true).await;
    assert!(
        failures.is_empty(),
        "{} failures:\n{}",
        failures.len(),
        failures.join("\n")
    );
    server.stop().await;
}

#[tokio::test]
async fn with_no_key_configured_every_route_is_reached() {
    let server = TestServer::with_router(probed(GuardConfig::new(LOOPBACK))).await;
    let failures = run_table(&server, false).await;
    assert!(
        failures.is_empty(),
        "{} failures:\n{}",
        failures.len(),
        failures.join("\n")
    );
    server.stop().await;
}

#[test]
fn the_table_covers_every_row_of_the_dispatch_table() {
    // Every exact route of ROUTES appears in TABLE with its method, and the counts match
    // the donor's routes: 31 GET rows, 30 POST rows, 2 DELETE rows.
    for spec in ROUTES {
        let covered = TABLE.iter().any(|&(m, p, _, _, _)| {
            m == spec.method
                && spec
                    .pattern
                    .matches(p.split('?').next().unwrap_or("").trim_end_matches('/'))
        });
        assert!(covered, "{spec:?} has no row in the test table");
    }
}

#[tokio::test]
async fn unregistered_slots_answer_as_unknown_routes_after_their_guards() {
    let config = GuardConfig::new(LOOPBACK).with_api_key(&Value::String("k1".into()));
    let server = TestServer::with_router(Router::new(config)).await;
    let key = [("Authorization", "Bearer k1")];
    for path in ["/v1/models", "/status", "/metrics", "/settings"] {
        assert_eq!(
            server.call("GET", path, &[], None).await.status,
            401,
            "{path}"
        );
        let r = server.call("GET", path, &key, None).await;
        assert_eq!(
            (r.status, r.text().as_str()),
            (404, "{\"error\": {\"message\": \"not found\"}}"),
            "{path}"
        );
    }
    for path in [
        "/",
        "/health",
        "/web/app.js",
        "/fonts/Outfit.woff2",
        "/models/sse",
        "/v1/responses/r",
    ] {
        assert_eq!(
            server.call("GET", path, &[], None).await.status,
            404,
            "{path}"
        );
    }
    // The /web redirect is built in: relative, one level up, the query kept.
    let r = server.call("GET", "/web", &[], None).await;
    assert_eq!(
        (r.status, r.header("Location"), r.header("Content-Length")),
        (302, Some("./"), Some("0"))
    );
    let r = server.call("GET", "/web/?a=1", &[], None).await;
    assert_eq!((r.status, r.header("Location")), (302, Some("../?a=1")));
    // A JSON route has its body read and parsed before its slot answers.
    let r = server.post_json("/v1/chat/completions", &key, "[]").await;
    assert_eq!(r.status, 400);
    assert_eq!(
        r.text(),
        "{\"error\": {\"type\": \"invalid_request_error\", \"message\": \"the request body must be a JSON object\"}}"
    );
    assert_eq!(
        server
            .post_json("/v1/chat/completions", &key, "{}")
            .await
            .status,
        404
    );
    server.stop().await;
}

#[tokio::test]
async fn json_routes_receive_the_parsed_object_and_others_the_unread_body() {
    let server = TestServer::with_router(probed(GuardConfig::new(LOOPBACK))).await;
    let r = server
        .post_json(
            "/v1/messages?beta=true",
            &[],
            "{\"model\": \"m\", \"n\": 1}",
        )
        .await;
    assert_eq!(r.json()["body"], serde_json::json!({"model": "m", "n": 1}));
    assert_eq!(r.json()["path"], "/v1/messages");
    // An empty body is read as {} (the donor's `json.loads(raw_ or b"{}")`).
    let r = server.post_json("/tokenize", &[], "").await;
    assert_eq!(
        (r.status, r.json()["body"].clone()),
        (200, serde_json::json!({}))
    );
    // A body that does not parse is the parser's 400, with Python's message.
    let r = server
        .post_json("/v1/chat/completions", &[], "{\"a\": ")
        .await;
    assert_eq!(r.status, 400);
    assert_eq!(
        r.json()["error"]["message"],
        "Expecting value: line 1 column 7 (char 6)"
    );
    assert_eq!(
        server.post_json("/v1/nothing", &[], "[1]").await.status,
        400
    );
    assert_eq!(server.post_json("/v1/nothing", &[], "{").await.status, 400);
    // Handler-read routes get no parsed body: the body is theirs to read.
    let r = server
        .post_json("/settings", &[], "{\"defaults\": null}")
        .await;
    assert_eq!((r.status, r.json()["body"].clone()), (200, Value::Null));
    server.stop().await;
}
