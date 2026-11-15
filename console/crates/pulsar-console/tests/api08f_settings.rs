//! Provenance: translated from project-maya serve/test_server.py::StallWatchdog::test_the_config_env_reaches_the_server at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! The transport's three settings (listen backlog, body limit, request timeout) from a run
//! config's `env` block and the environment to the listener that `pulsar_console::start`
//! binds (follow-up API-08F of API-08 and API-15). The donor's `apply_server_env` writes
//! the config's entries into `os.environ`, so a config entry that is not `null` wins over
//! the process environment, and an entry the config does not set (or sets to `null`)
//! leaves the environment's value in force. Only the names of the donor's `SERVER_ENV` are
//! applied: the backlog and the body limit are among them, the request timeout is not (a
//! config entry for it goes to the engine child, and the server keeps the environment's
//! value). The donor's `MAYA_*` names are re-expressed
//! under their `PULSAR_CONSOLE_*` names (decision B2, deviation BRAND-1).
//!
//! The settings are read from the started server ([`Started::transport`], the listener's
//! own settings), and the body limit and the timeout by behavior as well: a body over the
//! limit is answered 413, and a stalled request is closed after the timeout. The timeout
//! test runs on the real clock with a timeout of one second (a paused tokio clock cannot
//! drive a test whose other side is a real socket); it asserts a lower bound and a generous
//! upper bound.
//!
//! The stall seconds of the donor test (`ENGINE_STALL_S`) have no reader before the stall
//! watchdog of ENG-08 (M3); console-core's API-15 test asserts the resolved field.

use std::collections::BTreeMap;
use std::time::{Duration, Instant};

use console_core::config::{load_document, names, EnvSettings};
use console_core::fifo::FifoLog;
use console_http::transport::TransportConfig;
use console_testkit::server::TempDir;
use pulsar_console::{scripted_factory, start, Console, Exit, Options, Started};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;

fn opts(args: &[&str]) -> Options {
    let args: Vec<String> = args.iter().map(|a| (*a).to_owned()).collect();
    match pulsar_console::cli::parse(&args) {
        Ok(pulsar_console::Parsed::Run(o)) => o,
        other => panic!("{args:?}: {other:?}"),
    }
}

fn env(pairs: &[(&str, &str)]) -> BTreeMap<String, String> {
    pairs
        .iter()
        .map(|(k, v)| ((*k).to_owned(), (*v).to_owned()))
        .collect()
}

/// A temporary folder holding a run config with this text, and the config's path.
fn config_file(text: &str) -> (TempDir, String) {
    let dir = match TempDir::new("api08f") {
        Ok(d) => d,
        Err(e) => panic!("temp dir: {e}"),
    };
    let path = dir.path().join("pulsar-test.json");
    if let Err(e) = std::fs::write(&path, text) {
        panic!("write: {e}");
    }
    let path = path.to_string_lossy().into_owned();
    (dir, path)
}

/// Starts the server in process on port 0 with this run config text and environment.
async fn started(config_text: &str, env: &BTreeMap<String, String>) -> (Started, TempDir) {
    let (dir, path) = config_file(config_text);
    let (out, out_lines) = FifoLog::capture();
    let (err, err_lines) = FifoLog::capture();
    let console = Console { out, err };
    match start(
        &opts(&["--port", "0", "--config", &path]),
        scripted_factory,
        &console,
        env,
    )
    .await
    {
        Ok(s) => (s, dir),
        Err(Exit(code)) => panic!(
            "exit {code}: {:?} {:?}",
            out_lines.lines(),
            err_lines.lines()
        ),
    }
}

/// Serves `started` in the background; the returned sender stops it.
fn serve(started: Started) -> (std::net::SocketAddr, tokio::sync::oneshot::Sender<()>) {
    let addr = started.addr();
    let (stop, stopped) = tokio::sync::oneshot::channel::<()>();
    tokio::spawn(started.serve(async move {
        let _ = stopped.await;
    }));
    (addr, stop)
}

/// A chat request head announcing a body of `length` bytes, sent without the body.
async fn announce_body(
    addr: std::net::SocketAddr,
    length: u64,
) -> console_testkit::raw::RawResponse {
    let head = format!(
        "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: {length}\r\n\r\n"
    );
    console_testkit::raw::exchange(addr, head.as_bytes()).await
}

/// How long the server takes to close a connection that sent half a request head, and
/// what it wrote before closing (`None` when it was still open after `limit`).
async fn stalled_head(addr: std::net::SocketAddr, limit: Duration) -> (Option<Vec<u8>>, Duration) {
    let mut stream = match TcpStream::connect(addr).await {
        Ok(s) => s,
        Err(e) => panic!("connect: {e}"),
    };
    if let Err(e) = stream
        .write_all(b"POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1\r\n")
        .await
    {
        panic!("write: {e}");
    }
    let begun = Instant::now();
    let mut raw = Vec::new();
    let read = tokio::time::timeout(limit, stream.read_to_end(&mut raw)).await;
    let waited = begun.elapsed();
    match read {
        Ok(_) => (Some(raw), waited),
        Err(_) => (None, waited),
    }
}

const ALL_THREE_IN_THE_CONFIG: &str = "{\"env\": {\
    \"PULSAR_CONSOLE_HTTP_BACKLOG\": \"64\", \
    \"PULSAR_CONSOLE_MAX_BODY_MIB\": \"1\", \
    \"PULSAR_CONSOLE_REQUEST_TIMEOUT_S\": \"30\"}}";

// Donor: serve/test_server.py::StallWatchdog::test_the_config_env_reaches_the_server
#[tokio::test]
async fn a_run_config_env_block_reaches_the_bound_listener_over_the_environment() {
    // The same names in the environment, with other values. The backlog and the body
    // limit are in the donor's `SERVER_ENV`: the config's entries win, as
    // `apply_server_env` writes them over `os.environ`. The request timeout is not in
    // `SERVER_ENV`: the config's entry goes to the engine child, and the environment's
    // value stays in force for the server.
    let process = env(&[
        (names::HTTP_BACKLOG, "300"),
        (names::MAX_BODY_MIB, "8"),
        (names::REQUEST_TIMEOUT_S, "1"),
    ]);
    let (server, _dir) = started(ALL_THREE_IN_THE_CONFIG, &process).await;
    // The donor asserts `Server.request_queue_size`: the backlog the listener is opened
    // with.
    assert_eq!(
        server.transport(),
        TransportConfig {
            backlog: 64,
            max_body_bytes: 1 << 20,
            request_timeout: Duration::from_secs(1),
        }
    );
    let (addr, stop) = serve(server);
    // The body limit by behavior: 1 MiB from the config, not 8 MiB from the environment.
    let r = announce_body(addr, 2 << 20).await;
    assert_eq!(r.status, 413);
    assert!(r.text().contains("larger than 1 MiB"), "{}", r.text());
    // The timeout by behavior: closed unanswered after 1 s (the environment), not 30 s
    // (the config).
    let (raw, waited) = stalled_head(addr, Duration::from_secs(10)).await;
    assert_eq!(raw, Some(Vec::new()), "closed without an answer");
    assert!(
        waited >= Duration::from_millis(990) && waited < Duration::from_secs(6),
        "{waited:?}"
    );
    let _ = stop.send(());
}

#[tokio::test]
async fn the_environment_applies_where_the_run_config_sets_nothing() {
    // A `null` entry is not applied (`if v is not None`), and an absent one leaves the
    // environment's value in force.
    let process = env(&[
        (names::HTTP_BACKLOG, "300"),
        (names::MAX_BODY_MIB, "8"),
        (names::REQUEST_TIMEOUT_S, "30"),
    ]);
    let (server, _dir) = started(
        "{\"env\": {\"PULSAR_CONSOLE_HTTP_BACKLOG\": null}}",
        &process,
    )
    .await;
    assert_eq!(
        server.transport(),
        TransportConfig {
            backlog: 300,
            max_body_bytes: 8 << 20,
            request_timeout: Duration::from_secs(30),
        }
    );
    let (addr, stop) = serve(server);
    let r = announce_body(addr, 9 << 20).await;
    assert_eq!(r.status, 413);
    assert!(r.text().contains("larger than 8 MiB"), "{}", r.text());
    let _ = stop.send(());
}

#[tokio::test]
async fn the_listener_uses_the_resolved_settings_at_their_bounds() {
    // A JSON number is copied as Python's `str()` of it; a backlog beyond the platform's
    // `int` is clamped there; a body limit of 0 is the default 256 MiB; an infinite
    // timeout is no practical limit; an unparsable environment value falls back.
    let text = "{\"env\": {\
        \"PULSAR_CONSOLE_HTTP_BACKLOG\": 99999999999, \
        \"PULSAR_CONSOLE_MAX_BODY_MIB\": \"0\"}}";
    let process = env(&[
        (names::REQUEST_TIMEOUT_S, "inf"),
        (names::MAX_BODY_MIB, "soon"),
    ]);
    let (server, dir) = started(text, &process).await;
    let expected = TransportConfig {
        backlog: i32::MAX as u32,
        max_body_bytes: 256 << 20,
        request_timeout: Duration::MAX,
    };
    assert_eq!(server.transport(), expected);
    // The same values the server's resolved settings report: one source of truth.
    let cfg = match load_document(&dir.path().join("pulsar-test.json")) {
        Ok(c) => c,
        Err(e) => panic!("config: {e}"),
    };
    let resolved = match EnvSettings::resolve(&process, &cfg) {
        Ok(s) => s,
        Err(e) => panic!("resolve: {e}"),
    };
    assert_eq!(
        (
            resolved.http_backlog,
            resolved.max_body_mib,
            resolved.request_timeout_s
        ),
        (99_999_999_999, 256, f64::INFINITY)
    );
    assert_eq!(TransportConfig::from_settings(&resolved), expected);
    let (_addr, stop) = serve(server);
    let _ = stop.send(());
}
