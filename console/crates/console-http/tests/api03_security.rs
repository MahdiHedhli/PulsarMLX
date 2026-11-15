//! The SEC-1 security posture at the router, over raw sockets: the `Host` allowlist against
//! DNS rebinding (SEC-1.1, as the owner settled it on 2026-11-14), `Origin` on every route
//! with `Origin: null` foreign (SEC-1.2), a JSON content type on every POST (SEC-1.3), and
//! API keys (SEC-1.5). SEC-1.4 needs a client address that is not loopback, which a test on
//! loopback sockets cannot have; it is pinned in the router's unit tests
//! (`router::tests::admin_routes_need_a_loopback_client_or_a_key`).
//!
//! Several cases reuse the archived PulsarMLX serving crate's raw-HTTP tests (tag
//! `archive/2026-09-21/feat/openai-serving`, `crates/serve-synthetic/tests/raw_http.rs`,
//! PulsarMLX's own code), as decision B8 directs; each says which.
//!
//! The tests choose the guard's bind address independently of the socket, so a
//! non-loopback bind is tested while the server listens on loopback.

use std::net::{IpAddr, Ipv4Addr};

use console_http::guard::{GuardConfig, HOST_REFUSED_MESSAGE};
use console_http::router::Router;
use console_testkit::raw::*;
use console_testkit::server::probe::probed;
use console_testkit::server::{TestServer, LOOPBACK};
use serde_json::Value;

const ANY: IpAddr = IpAddr::V4(Ipv4Addr::UNSPECIFIED);
const LAN: IpAddr = IpAddr::V4(Ipv4Addr::new(192, 0, 2, 1));

fn host_refused_body() -> String {
    format!("{{\"error\": {{\"type\": \"permission_error\", \"message\": \"{HOST_REFUSED_MESSAGE}\"}}}}")
}

async fn health_with_host(server: &TestServer, host: &str) -> RawResponse {
    server.call("GET", "/health", &[("Host", host)], None).await
}

// SEC-1.1: on a loopback bind only the loopback names, with any port, pass by default.
#[tokio::test]
async fn rebinding_a_loopback_bind_serves_only_loopback_names() {
    let server = TestServer::with_router(probed(GuardConfig::new(LOOPBACK))).await;
    let port = server.addr.port();
    for host in [
        format!("127.0.0.1:{port}"),
        format!("localhost:{port}"),
        format!("[::1]:{port}"),
        "localhost".to_owned(),
        "127.0.0.1:1".to_owned(),
        "[::1]:65535".to_owned(),
        format!("LOCALHOST:{port}"),
    ] {
        let r = health_with_host(&server, &host).await;
        assert_eq!(
            (r.status, r.routed().as_deref()),
            (200, Some("Health")),
            "{host}"
        );
    }
    // From the archived crate's host_origin_auth_and_header_limits_are_enforced: a
    // rebinding name is refused, here with 403 permission_error before routing.
    for host in [
        "attacker.invalid".to_owned(),
        format!("attacker.invalid:{port}"),
        "127.0.0.2".to_owned(),
        format!("[0:0:0:0:0:0:0:1]:{port}"),
        format!("[::ffff:127.0.0.1]:{port}"),
        format!("localhost.:{port}"),
        "localhost:99999".to_owned(),
        "pulsar.local".to_owned(),
        String::new(),
    ] {
        let r = health_with_host(&server, &host).await;
        assert_eq!(r.status, 403, "{host:?}");
        assert_eq!(r.text(), host_refused_body(), "{host:?}");
        assert_eq!(r.routed(), None);
    }
    server.stop().await;
}

// SEC-1.1, from the archived crate's duplicate_host_headers_are_rejected: exactly one Host
// header is required, and a missing one is refused too.
#[tokio::test]
async fn rebinding_exactly_one_host_header() {
    let server = TestServer::with_router(probed(GuardConfig::new(LOOPBACK))).await;
    let port = server.addr.port();
    let raw = |hosts: &[String]| {
        let mut text = String::from("GET /health HTTP/1.1\r\n");
        for h in hosts {
            text.push_str(&format!("Host: {h}\r\n"));
        }
        text.push_str("Connection: close\r\n\r\n");
        text.into_bytes()
    };
    let one = format!("127.0.0.1:{port}");
    let other = format!("localhost:{port}");
    assert_eq!(
        exchange(server.addr, &raw(&[one.clone(), other]))
            .await
            .status,
        403
    );
    assert_eq!(
        exchange(server.addr, &raw(&[one.clone(), one.clone()]))
            .await
            .status,
        403
    );
    assert_eq!(exchange(server.addr, &raw(&[])).await.status, 403);
    assert_eq!(exchange(server.addr, &raw(&[one])).await.status, 200);
    // An HTTP/0.9 request carries no headers at all, so no Host: refused (the answer is
    // the body alone, as Python writes HTTP/0.9 answers).
    let r = exchange(server.addr, b"GET /health\r\n").await;
    assert_eq!(String::from_utf8_lossy(&r.raw), host_refused_body());
    server.stop().await;
}

// SEC-1.1: allowed_hosts extends the names on a loopback bind; a listed port is exact.
#[tokio::test]
async fn rebinding_allowed_hosts_extend_a_loopback_bind() {
    let hosts = Some(vec!["pulsar.local".to_owned(), "Box.LAN:8095".to_owned()]);
    let server =
        TestServer::with_router(probed(GuardConfig::new(LOOPBACK).with_allowed_hosts(hosts))).await;
    for (host, want) in [
        ("pulsar.local", 200),
        ("pulsar.local:8095", 200),
        ("PULSAR.LOCAL:1", 200),
        ("box.lan:8095", 200),
        ("box.lan:8096", 403),
        ("box.lan", 403),
        ("localhost:8095", 200),
        ("evil.example", 403),
    ] {
        assert_eq!(health_with_host(&server, host).await.status, want, "{host}");
    }
    server.stop().await;
}

// SEC-1.1: on a non-loopback bind Host is not restricted, as in the donor.
#[tokio::test]
async fn rebinding_a_non_loopback_bind_is_unrestricted_without_a_list() {
    for bind in [ANY, LAN] {
        let server = TestServer::with_router(probed(GuardConfig::new(bind))).await;
        for host in ["evil.example", "192.0.2.1:8095", "localhost", "[fe80::1]:1"] {
            assert_eq!(
                health_with_host(&server, host).await.status,
                200,
                "{bind} {host}"
            );
        }
        let r = exchange(server.addr, b"GET /health HTTP/1.1\r\n\r\n").await;
        assert_eq!(r.status, 200, "{bind}: a missing Host is not checked");
        server.stop().await;
    }
}

// SEC-1.1: on a non-loopback bind with allowed_hosts set, only its names and the loopback
// names pass; an empty list leaves only the loopback names.
#[tokio::test]
async fn rebinding_a_non_loopback_bind_with_a_list() {
    let hosts = Some(vec!["box.lan".to_owned()]);
    let server =
        TestServer::with_router(probed(GuardConfig::new(ANY).with_allowed_hosts(hosts))).await;
    for (host, want) in [
        ("box.lan:8095", 200),
        ("127.0.0.1:8095", 200),
        ("[::1]", 200),
        ("192.0.2.1:8095", 403),
        ("evil.example", 403),
    ] {
        assert_eq!(health_with_host(&server, host).await.status, want, "{host}");
    }
    server.stop().await;
    let server = TestServer::with_router(probed(
        GuardConfig::new(LAN).with_allowed_hosts(Some(Vec::new())),
    ))
    .await;
    assert_eq!(health_with_host(&server, "localhost:1").await.status, 200);
    assert_eq!(
        health_with_host(&server, "192.0.2.1:8095").await.status,
        403
    );
    server.stop().await;
}

// SEC-1.1: the Host check comes before every other guard and every method, and a refused
// Host gets no CORS grant.
#[tokio::test]
async fn rebinding_the_host_check_comes_first() {
    let config = GuardConfig::new(LOOPBACK)
        .with_api_key(&Value::String("k1".into()))
        .with_cors_origins(vec!["*".to_owned()]);
    let server = TestServer::with_router(probed(config)).await;
    let evil = ("Host", "attacker.invalid:8095");
    for (method, path) in [
        ("GET", "/v1/models"),
        ("GET", "/nothing"),
        ("POST", "/v1/chat/completions"),
        ("DELETE", "/v1/responses/r"),
        ("OPTIONS", "/v1/chat/completions"),
    ] {
        let r = server
            .call(
                method,
                path,
                &[evil, ("Origin", "http://attacker.invalid")],
                None,
            )
            .await;
        assert_eq!(r.status, 403, "{method} {path}");
        assert_eq!(r.text(), host_refused_body(), "{method} {path}");
        assert_eq!(
            r.header("Access-Control-Allow-Origin"),
            None,
            "{method} {path}"
        );
    }
    // The same requests with a loopback Host reach their own guards.
    let r = server
        .call("GET", "/v1/models", &[("Origin", "http://x.example")], None)
        .await;
    assert_eq!(
        (r.status, r.header("Access-Control-Allow-Origin")),
        (401, Some("*"))
    );
    server.stop().await;
}

// SEC-1.2: Origin is checked on every route, GET included, and Origin: null is foreign.
#[tokio::test]
async fn origin_is_checked_on_every_route() {
    let server = TestServer::with_router(probed(GuardConfig::new(LOOPBACK))).await;
    let own = format!("http://{}", server.host());
    for path in [
        "/",
        "/health",
        "/web/app.js",
        "/v1/models",
        "/nothing",
        "/v1/strata/stream",
    ] {
        for origin in ["http://evil.example", "null", "https://evil.example:443"] {
            let r = server.call("GET", path, &[("Origin", origin)], None).await;
            assert_eq!(r.status, 403, "{path} {origin}");
            assert_eq!(
                r.json()["error"]["message"],
                "requests from other web pages are refused (the config's cors_origins lists the pages allowed)"
            );
        }
        assert_ne!(
            server
                .call("GET", path, &[("Origin", &own)], None)
                .await
                .status,
            403,
            "{path}"
        );
        assert_ne!(
            server
                .call("GET", path, &[("Origin", "")], None)
                .await
                .status,
            403,
            "{path}"
        );
    }
    // With cors_origins, a listed page passes on /v1/* only, and null is not a listed page
    // unless "*" allows every page.
    let config =
        GuardConfig::new(LOOPBACK).with_cors_origins(vec!["http://127.0.0.1:8090".to_owned()]);
    let server2 = TestServer::with_router(probed(config)).await;
    let page = [("Origin", "http://127.0.0.1:8090")];
    assert_eq!(
        server2.call("GET", "/v1/models", &page, None).await.status,
        200
    );
    assert_eq!(
        server2.call("GET", "/health", &page, None).await.status,
        403
    );
    assert_eq!(
        server2
            .call("GET", "/v1/models", &[("Origin", "null")], None)
            .await
            .status,
        403
    );
    server2.stop().await;
    server.stop().await;
}

// SEC-1.3, from the archived crate's malformed_json_and_unsupported_content_type_are_rejected:
// well-formed JSON with another media type is refused (with the donor's 415 answer); a
// charset parameter is accepted.
#[tokio::test]
async fn every_post_needs_a_json_content_type() {
    let server = TestServer::with_router(probed(GuardConfig::new(LOOPBACK))).await;
    let body = b"{\"model\": \"m\"}";
    for path in [
        "/v1/chat/completions",
        "/v1/strata/cancel",
        "/api/show",
        "/models/unload",
        "/v1/nothing",
    ] {
        for ctype in [
            Some("text/plain"),
            Some("application/x-www-form-urlencoded"),
            Some("*/*"),
            Some("application/jsonx"),
            None,
        ] {
            let headers: Vec<(&str, &str)> =
                ctype.map(|c| vec![("Content-Type", c)]).unwrap_or_default();
            let r = server.call("POST", path, &headers, Some(body)).await;
            assert_eq!(r.status, 415, "{path} {ctype:?}");
            assert_eq!(
                r.text(),
                "{\"error\": {\"message\": \"send application/json\"}}"
            );
        }
        for ctype in ["application/json; charset=utf-8", "Application/JSON"] {
            let r = server
                .call("POST", path, &[("Content-Type", ctype)], Some(body))
                .await;
            assert_ne!(r.status, 415, "{path} {ctype}");
        }
    }
    // The attachment route takes raw bytes and keeps its own check (its handler's).
    let r = server
        .call(
            "POST",
            "/attach",
            &[("Content-Type", "application/pdf")],
            Some(b"%PDF"),
        )
        .await;
    assert_eq!((r.status, r.routed().as_deref()), (200, Some("Attach")));
    // The body is read before the 415, as the donor's own-page routes read it: a body over
    // the limit is answered 413 first.
    let r = server
        .call(
            "POST",
            "/v1/chat/completions",
            &[
                ("Content-Type", "text/plain"),
                ("Content-Length", "300000000000"),
            ],
            None,
        )
        .await;
    assert_eq!(r.status, 413);
    // The key and the foreign page are checked before the content type, as the donor's
    // do_POST checks them first.
    let keyed = TestServer::with_router(probed(
        GuardConfig::new(LOOPBACK).with_api_key(&Value::String("k1".into())),
    ))
    .await;
    let r = keyed
        .call(
            "POST",
            "/v1/chat/completions",
            &[("Content-Type", "text/plain")],
            Some(body),
        )
        .await;
    assert_eq!(r.status, 401);
    let r = keyed
        .call(
            "POST",
            "/v1/chat/completions",
            &[
                ("Content-Type", "text/plain"),
                ("Authorization", "Bearer k1"),
                ("Origin", "http://evil.example"),
            ],
            Some(body),
        )
        .await;
    assert_eq!(r.status, 403);
    keyed.stop().await;
    server.stop().await;
}

// SEC-1.5: keys from the archived crate's host_origin_auth_and_header_limits_are_enforced
// (a wrong bearer key is 401) and the donor's forms (bearer in any case, x-api-key).
#[tokio::test]
async fn api_keys_in_their_accepted_forms() {
    let server = TestServer::with_router(Router::new(
        GuardConfig::new(LOOPBACK).with_api_key(&Value::String("k1".into())),
    ))
    .await;
    let get = |headers: Vec<(&'static str, &'static str)>| {
        let server = &server;
        async move {
            server
                .call("GET", "/v1/models", &headers, None)
                .await
                .status
        }
    };
    assert_eq!(get(vec![("Authorization", "Bearer wrong-key")]).await, 401);
    assert_eq!(get(vec![]).await, 401);
    assert_eq!(get(vec![("Authorization", "Bearer k1")]).await, 404);
    assert_eq!(get(vec![("Authorization", "bearer   k1  ")]).await, 404);
    assert_eq!(get(vec![("x-api-key", "k1")]).await, 404);
    // x-api-key is taken as it arrives: the header parser drops leading whitespace only.
    assert_eq!(get(vec![("x-api-key", "k1 ")]).await, 401);
    assert_eq!(
        get(vec![("Authorization", "Basic k1"), ("x-api-key", "k1")]).await,
        404
    );
    assert_eq!(
        get(vec![("Authorization", "Bearer k2"), ("x-api-key", "k1")]).await,
        401
    );
    server.stop().await;
}

// The CORS headers come from the transport's end-headers hook, so they reach the answers
// the transport writes itself: here the 501 page of an unserved method.
#[tokio::test]
async fn cors_headers_reach_the_transports_own_pages() {
    let server = TestServer::with_router(Router::new(
        GuardConfig::new(LOOPBACK).with_cors_origins(vec!["http://127.0.0.1:8090".to_owned()]),
    ))
    .await;
    let r = server
        .call(
            "PUT",
            "/v1/models",
            &[("Origin", "http://127.0.0.1:8090")],
            None,
        )
        .await;
    assert_eq!(r.status, 501);
    assert_eq!(
        r.header("Access-Control-Allow-Origin"),
        Some("http://127.0.0.1:8090")
    );
    assert_eq!(r.header("Vary"), Some("Origin"));
    // And to the 404 of an unknown /v1/ route.
    let r = server
        .call(
            "GET",
            "/v1/nothing",
            &[("Origin", "http://127.0.0.1:8090")],
            None,
        )
        .await;
    assert_eq!(
        (r.status, r.header("Access-Control-Allow-Origin")),
        (404, Some("http://127.0.0.1:8090"))
    );
    server.stop().await;
}
