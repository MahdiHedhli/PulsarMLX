//! Donor tests of work package API-03, re-expressed against the router.
//!
//! Provenance: translated from project-maya serve/test_server.py::CorsOptIn, serve/test_server.py::RequestBodies::test_several_api_keys, serve/test_server.py::WebApp::test_discovery_needs_the_api_key, serve/test_server.py::WebApp::test_metrics_need_the_key_when_one_is_set, serve/test_server.py::SharedSettings::test_only_strata_s_own_page_may_set_them, serve/test_server.py::SharedSettings::test_they_need_the_key_when_one_is_set, serve/test_server.py::ModelManagement::test_the_api_key_guards_them_and_status and serve/test_server.py::ClientShapes::test_query_string at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! The donor's methods run against a full server. Here the route handlers of later packages
//! do not exist yet, so the test kit's `RouteProbe` stands in for them where a method needs a
//! route to answer. A method whose assertions are all about the router and its guards is
//! re-expressed in full; a method that also asserts what a later package's handler answers
//! (a chat answer, a model listing, a settings value) is re-expressed in its router part,
//! and its ledger row stays pending until that package lands (each test says so).

use console_core::config::parse_cors_origins;
use console_http::guard::{GuardConfig, FOREIGN_PAGE_MESSAGE};
use console_http::router::Router;
use console_testkit::server::probe::probed;
use console_testkit::server::{TestServer, LOOPBACK};
use serde_json::{json, Value};

const PAGE: &str = "http://127.0.0.1:8090";
const CHAT: &str = "{\"model\": \"m\", \"messages\": [{\"role\": \"user\", \"content\": \"hi\"}]}";

fn cors(origins: &[&str]) -> GuardConfig {
    GuardConfig::new(LOOPBACK).with_cors_origins(origins.iter().map(|o| (*o).to_owned()).collect())
}

fn keyed(setting: Value) -> GuardConfig {
    GuardConfig::new(LOOPBACK).with_api_key(&setting)
}

// Donor: serve/test_server.py::CorsOptIn::test_without_the_setting_nothing_changes
// Deviation SEC-1.2: the donor answers the GET 200 (it checks `Origin` only on POST and
// DELETE); here every route refuses a page that is neither this server nor CORS-allowed,
// so the GET is 403. The other assertions are the donor's: no CORS header either way.
#[tokio::test]
async fn cors_without_the_setting_nothing_changes() {
    let server = TestServer::with_router(probed(cors(&[]))).await;
    let r = server
        .call(
            "OPTIONS",
            "/v1/chat/completions",
            &[("Origin", PAGE), ("Access-Control-Request-Method", "POST")],
            None,
        )
        .await;
    assert_eq!(r.status, 403);
    assert_eq!(r.header("Access-Control-Allow-Origin"), None);
    assert_eq!(r.header("Content-Length"), Some("0"));
    assert!(r.body.is_empty());
    let r = server
        .call("GET", "/v1/models", &[("Origin", PAGE)], None)
        .await;
    assert_eq!(
        r.status, 403,
        "SEC-1.2: a foreign page is refused on GET too"
    );
    assert_eq!(r.json()["error"]["type"], "permission_error");
    assert_eq!(r.header("Access-Control-Allow-Origin"), None);
    // Without an Origin the route is reached, as in the donor.
    assert_eq!(
        server.call("GET", "/v1/models", &[], None).await.status,
        200
    );
    server.stop().await;
}

// Donor: serve/test_server.py::CorsOptIn::test_a_listed_page_gets_its_preflight_and_the_header
// Router part only: the 200 answers of /v1/models (API-11) and of a streamed chat
// completion (API-07, API-08) come from the probe here; the ledger row stays pending.
#[tokio::test]
async fn cors_a_listed_page_gets_its_preflight_and_the_header() {
    let server = TestServer::with_router(probed(cors(&[PAGE]))).await;
    let r = server
        .call(
            "OPTIONS",
            "/v1/chat/completions",
            &[
                ("Origin", PAGE),
                ("Access-Control-Request-Method", "POST"),
                (
                    "Access-Control-Request-Headers",
                    "content-type,authorization",
                ),
            ],
            None,
        )
        .await;
    assert_eq!(r.status, 204);
    assert_eq!(r.header("Access-Control-Allow-Origin"), Some(PAGE));
    assert_eq!(r.header("Vary"), Some("Origin"));
    assert!(r
        .header("Access-Control-Allow-Methods")
        .is_some_and(|m| m.contains("POST")));
    assert_eq!(
        r.header("Access-Control-Allow-Headers"),
        Some("content-type,authorization")
    );
    // The donor's exact head: methods, headers, max age, length, then the CORS headers.
    let names: Vec<&str> = r.headers.iter().map(|(k, _)| k.as_str()).collect();
    assert_eq!(
        names,
        [
            "Server",
            "Date",
            "Access-Control-Allow-Methods",
            "Access-Control-Allow-Headers",
            "Access-Control-Max-Age",
            "Content-Length",
            "Access-Control-Allow-Origin",
            "Vary"
        ]
    );
    assert_eq!(r.header("Access-Control-Max-Age"), Some("600"));
    let r = server
        .call("GET", "/v1/models", &[("Origin", PAGE)], None)
        .await;
    assert_eq!(
        (r.status, r.header("Access-Control-Allow-Origin")),
        (200, Some(PAGE))
    );
    let r = server
        .post_json("/v1/chat/completions", &[("Origin", PAGE)], CHAT)
        .await;
    assert_eq!(
        (r.status, r.header("Access-Control-Allow-Origin")),
        (200, Some(PAGE))
    );
    server.stop().await;
}

// Donor: serve/test_server.py::CorsOptIn::test_another_page_gets_nothing
#[tokio::test]
async fn cors_another_page_gets_nothing() {
    let server = TestServer::with_router(probed(cors(&[PAGE]))).await;
    for origin in ["http://evil.example", "http://127.0.0.1:8091"] {
        let r = server
            .call("OPTIONS", "/v1/models", &[("Origin", origin)], None)
            .await;
        assert_eq!(r.status, 403, "{origin}");
        assert_eq!(r.header("Access-Control-Allow-Origin"), None, "{origin}");
        let r = server
            .call("GET", "/v1/models", &[("Origin", origin)], None)
            .await;
        assert_eq!(r.header("Access-Control-Allow-Origin"), None, "{origin}");
        // (SEC-1.2: the GET itself is refused; the donor asserts only the header.)
        assert_eq!(r.status, 403, "{origin}");
    }
    server.stop().await;
}

// Donor: serve/test_server.py::CorsOptIn::test_a_trailing_slash_in_the_config_is_forgiven
#[tokio::test]
async fn cors_a_trailing_slash_in_the_config_is_forgiven() {
    let origins = match parse_cors_origins(Some(&json!([format!("{PAGE}/")]))) {
        Ok(origins) => origins,
        Err(e) => panic!("parse_cors_origins: {e}"),
    };
    assert_eq!(origins, vec![PAGE.to_owned()]);
    let server = TestServer::with_router(probed(
        GuardConfig::new(LOOPBACK).with_cors_origins(origins),
    ))
    .await;
    let r = server
        .call("GET", "/v1/models", &[("Origin", PAGE)], None)
        .await;
    assert_eq!(r.header("Access-Control-Allow-Origin"), Some(PAGE));
    server.stop().await;
}

// Donor: serve/test_server.py::CorsOptIn::test_star_allows_every_page
// Router part only: the 200 of /v1/models is API-11's; the ledger row stays pending.
#[tokio::test]
async fn cors_star_allows_every_page() {
    let server = TestServer::with_router(probed(cors(&["*"]))).await;
    let r = server
        .call(
            "GET",
            "/v1/models",
            &[("Origin", "http://anywhere.example")],
            None,
        )
        .await;
    assert_eq!(
        (r.status, r.header("Access-Control-Allow-Origin")),
        (200, Some("*"))
    );
    assert_eq!(r.header("Vary"), None);
    server.stop().await;
}

// Donor: serve/test_server.py::CorsOptIn::test_settings_and_the_page_itself_stay_closed
#[tokio::test]
async fn cors_settings_and_the_page_itself_stay_closed() {
    let server = TestServer::with_router(probed(cors(&[PAGE]))).await;
    let r = server
        .call("OPTIONS", "/settings", &[("Origin", PAGE)], None)
        .await;
    assert_eq!(r.status, 403);
    assert_eq!(r.header("Access-Control-Allow-Origin"), None);
    let r = server
        .post_json(
            "/settings",
            &[("Origin", PAGE)],
            "{\"defaults\": {\"temperature\": 1}}",
        )
        .await;
    assert_eq!(
        r.status, 403,
        "a listed page may chat, it may not change the settings"
    );
    assert_eq!(r.header("Access-Control-Allow-Origin"), None);
    assert_eq!(r.routed(), None);
    let r = server.call("GET", "/", &[("Origin", PAGE)], None).await;
    assert_eq!(r.header("Access-Control-Allow-Origin"), None);
    server.stop().await;
}

// Donor: serve/test_server.py::CorsOptIn::test_another_page_cannot_post_without_a_preflight
// Router part only: the 200 of a chat completion without an Origin is API-08's (here the
// probe answers); the ledger row stays pending.
#[tokio::test]
async fn cors_another_page_cannot_post_without_a_preflight() {
    let server = TestServer::with_router(probed(cors(&[]))).await;
    for origin in ["http://evil.example", "null"] {
        let r = server
            .call(
                "POST",
                "/v1/chat/completions",
                &[("Content-Type", "text/plain"), ("Origin", origin)],
                Some(CHAT.as_bytes()),
            )
            .await;
        assert_eq!(r.status, 403, "{origin}");
        assert_eq!(r.routed(), None, "{origin}");
    }
    let r = server.post_json("/v1/chat/completions", &[], CHAT).await;
    assert_eq!(
        (r.status, r.routed().as_deref()),
        (200, Some("ChatCompletions"))
    );
    let r = server
        .call(
            "DELETE",
            "/v1/responses/resp_x",
            &[("Origin", "http://evil.example")],
            None,
        )
        .await;
    assert_eq!(r.status, 403);
    server.stop().await;
}

// Donor: serve/test_server.py::RequestBodies::test_several_api_keys
// Router part only: the 200 answers are the chat completion's (API-08); here the probe
// answers once the key passes. The ledger row stays pending.
#[tokio::test]
async fn several_api_keys() {
    let server = TestServer::with_router(probed(keyed(json!("k1, k2")))).await;
    for (key, want) in [("k1", 200), ("k2", 200), ("k3", 401), ("k1, k2", 401)] {
        let auth = format!("Bearer {key}");
        let r = server
            .post_json("/v1/chat/completions", &[("Authorization", &auth)], CHAT)
            .await;
        assert_eq!(r.status, want, "{key}");
    }
    server.stop().await;
    // A list in the config: a key with a comma in it.
    let server = TestServer::with_router(probed(keyed(json!(["a,b"])))).await;
    let r = server
        .post_json(
            "/v1/chat/completions",
            &[("Authorization", "Bearer a,b")],
            CHAT,
        )
        .await;
    assert_eq!(r.status, 200);
    let r = server
        .post_json(
            "/v1/chat/completions",
            &[("Authorization", "Bearer a")],
            CHAT,
        )
        .await;
    assert_eq!(r.status, 401);
    server.stop().await;
}

// Donor: serve/test_server.py::WebApp::test_discovery_needs_the_api_key
// Router part only: the 200 answers are API-11's discovery routes; the ledger row stays
// pending.
#[tokio::test]
async fn discovery_needs_the_api_key() {
    let server = TestServer::with_router(probed(keyed(json!("secret")))).await;
    for path in ["/models", "/v1/models", "/props", "/slots"] {
        assert_eq!(
            server.call("GET", path, &[], None).await.status,
            401,
            "{path}"
        );
        let r = server
            .call("GET", path, &[("Authorization", "Bearer secret")], None)
            .await;
        assert_eq!(r.status, 200, "{path}");
    }
    server.stop().await;
}

// Donor: serve/test_server.py::WebApp::test_metrics_need_the_key_when_one_is_set
// Router part only: /metrics (API-06) and the page (API-12) answer through the probe; the
// ledger row stays pending.
#[tokio::test]
async fn metrics_need_the_key_when_one_is_set() {
    let server = TestServer::with_router(probed(keyed(json!("secret")))).await;
    assert_eq!(server.call("GET", "/metrics", &[], None).await.status, 401);
    let r = server
        .call(
            "GET",
            "/metrics",
            &[("Authorization", "Bearer secret")],
            None,
        )
        .await;
    assert_eq!(r.status, 200);
    // The page itself asks for the key, so it opens without one.
    let r = server.call("GET", "/", &[], None).await;
    assert_eq!((r.status, r.routed().as_deref()), (200, Some("Index")));
    server.stop().await;
}

// Donor: serve/test_server.py::SharedSettings::test_only_strata_s_own_page_may_set_them
// Router part only: the 400 for an out-of-range temperature and the unchanged settings are
// API-13's; the ledger row stays pending. The 403 is the donor's own do_POST foreign-page
// refusal (serve/server.py:6163, `_foreign_page` at 6141-6150 runs before `_settings`),
// unchanged, body included; only the 415 moves to the router (SEC-1.3, with the donor's
// message).
#[tokio::test]
async fn only_the_own_page_may_set_the_shared_settings() {
    let server = TestServer::with_router(probed(GuardConfig::new(LOOPBACK))).await;
    let body = "{\"defaults\": {\"temperature\": 1}}";
    let r = server
        .call(
            "POST",
            "/settings",
            &[("Content-Type", "text/plain")],
            Some(body.as_bytes()),
        )
        .await;
    assert_eq!(r.status, 415);
    assert_eq!(
        r.text(),
        "{\"error\": {\"message\": \"send application/json\"}}"
    );
    let r = server
        .post_json("/settings", &[("Origin", "http://evil.example")], body)
        .await;
    assert_eq!(r.status, 403);
    assert_eq!(
        r.text(),
        format!(
            "{{\"error\": {{\"type\": \"permission_error\", \"message\": \"{FOREIGN_PAGE_MESSAGE}\"}}}}"
        )
    );
    let own = format!("http://{}", server.host());
    let r = server
        .post_json("/settings", &[("Origin", &own)], body)
        .await;
    assert_eq!(
        (r.status, r.routed().as_deref()),
        (200, Some("SettingsPost"))
    );
    server.stop().await;
}

// Donor: serve/test_server.py::SharedSettings::test_they_need_the_key_when_one_is_set
// Router part only: the 200 is API-13's settings handler; the ledger row stays pending.
#[tokio::test]
async fn shared_settings_need_the_key_when_one_is_set() {
    let server = TestServer::with_router(probed(keyed(json!("secret")))).await;
    let body = "{\"defaults\": {\"temperature\": 1}}";
    assert_eq!(server.post_json("/settings", &[], body).await.status, 401);
    let r = server
        .post_json("/settings", &[("Authorization", "Bearer secret")], body)
        .await;
    assert_eq!(
        (r.status, r.routed().as_deref()),
        (200, Some("SettingsPost"))
    );
    server.stop().await;
}

// Donor: serve/test_server.py::ModelManagement::test_the_api_key_guards_them_and_status
// Router part only (the route-guard half): /models/load and /models/unload are keyed by the
// router, /models/sse by its handler (here the probe, which asks as the donor's handler
// does), /status by the router. The engine-side assertions and the 200 answers are
// API-11's and API-06's; the ledger row stays pending.
#[tokio::test]
async fn the_api_key_guards_model_management_and_status() {
    let server = TestServer::with_router(probed(keyed(json!("secret")))).await;
    let calls = [
        ("POST", "/models/load"),
        ("POST", "/models/unload"),
        ("GET", "/models/sse"),
        ("GET", "/status"),
    ];
    for (method, path) in calls {
        for key in [None, Some("Bearer wrong")] {
            let mut headers = vec![("Content-Type", "application/json")];
            if let Some(key) = key {
                headers.push(("Authorization", key));
            }
            let body = (method == "POST").then_some(&b"{}"[..]);
            let r = server.call(method, path, &headers, body).await;
            assert_eq!(r.status, 401, "{method} {path} {key:?}");
            assert_eq!(
                r.text(),
                "{\"error\": {\"type\": \"authentication_error\", \"message\": \"missing or wrong API key\"}}"
            );
        }
    }
    let key = [("Authorization", "Bearer secret")];
    assert_eq!(server.call("GET", "/status", &key, None).await.status, 200);
    assert_eq!(
        server.call("GET", "/models/sse", &key, None).await.status,
        200
    );
    server.stop().await;
    // No key set: open, as before.
    let server = TestServer::with_router(probed(GuardConfig::new(LOOPBACK))).await;
    assert_eq!(server.call("GET", "/status", &[], None).await.status, 200);
    server.stop().await;
}

// Donor: serve/test_server.py::ClientShapes::test_query_string
// Router part only: the three paths reach their dialect's slot with the query and the
// trailing slash dropped, and an unknown path with a query is 404. The 200 answers are
// API-08's and API-09's; the ledger row stays pending.
#[tokio::test]
async fn client_shapes_query_string() {
    let server = TestServer::with_router(probed(GuardConfig::new(LOOPBACK))).await;
    let body = "{\"model\": \"x\", \"max_tokens\": 20, \"messages\": [{\"role\": \"user\", \"content\": \"hi\"}]}";
    let anthropic = [("anthropic-version", "2023-06-01")];
    for (path, slot) in [
        ("/v1/messages?beta=true", "Messages"),
        ("/v1/chat/completions?api-version=1", "ChatCompletions"),
        ("/v1/messages/?beta=true", "Messages"),
    ] {
        let r = server.post_json(path, &anthropic, body).await;
        assert_eq!(
            (r.status, r.routed().as_deref()),
            (200, Some(slot)),
            "{path}"
        );
    }
    let r = server
        .post_json("/v1/nothing?beta=true", &anthropic, body)
        .await;
    assert_eq!(r.status, 404);
    server.stop().await;
    // With no handler at all the unknown path is still 404 and the known ones are routed.
    let server = TestServer::with_router(Router::new(GuardConfig::new(LOOPBACK))).await;
    assert_eq!(
        server
            .post_json("/v1/nothing?beta=true", &[], body)
            .await
            .status,
        404
    );
    server.stop().await;
}
