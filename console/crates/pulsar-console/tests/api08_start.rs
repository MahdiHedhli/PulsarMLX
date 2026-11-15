//! The start-up of the M1 entry point in process (`pulsar_console::start`), with the
//! console lines captured and the environment injected: what each step prints, the run
//! config and environment settings reaching the transport and the guards, and the
//! refusals at start (an unusable `allowed_hosts` entry, LD40; a config error; a port in
//! use; an engine that is not synthetic).

use std::collections::BTreeMap;
use std::sync::Arc;

use console_core::config::names;
use console_core::engine::{
    EngineFactory, EngineFailure, EngineInstance, EngineKind, EngineStartConfig,
};
use console_core::fifo::{FifoLog, LogCapture};
use console_core::sampling::sampling_defaults_from_config;
use console_engine::fake::doubles::NotSyntheticEngine;
use console_testkit::raw::RawRequest;
use console_testkit::server::TempDir;
use pulsar_console::{
    scripted_factory, start, Console, Exit, Options, Started, SYNTHETIC_ENGINE_LINE,
};
use serde_json::Value;
use tokio::sync::oneshot;

fn console() -> (Console, LogCapture, LogCapture) {
    let (out, out_lines) = FifoLog::capture();
    let (err, err_lines) = FifoLog::capture();
    (Console { out, err }, out_lines, err_lines)
}

fn opts(args: &[&str]) -> Options {
    let args: Vec<String> = args.iter().map(|a| (*a).to_owned()).collect();
    match pulsar_console::cli::parse(&args) {
        Ok(pulsar_console::Parsed::Run(o)) => o,
        other => panic!("{args:?}: {other:?}"),
    }
}

/// A started server serving in the background until the sender is dropped or used.
struct Running {
    addr: std::net::SocketAddr,
    stop: Option<oneshot::Sender<()>>,
    task: tokio::task::JoinHandle<()>,
}

impl Running {
    fn of(started: Started) -> Self {
        let addr = started.addr();
        let (stop, stopped) = oneshot::channel::<()>();
        let task = tokio::spawn(started.serve(async move {
            let _ = stopped.await;
        }));
        Self {
            addr,
            stop: Some(stop),
            task,
        }
    }

    async fn post(
        &self,
        headers: &[(&str, &str)],
        body: &str,
    ) -> console_testkit::raw::RawResponse {
        let mut r = RawRequest::post("/v1/chat/completions")
            .header("Host", &format!("127.0.0.1:{}", self.addr.port()));
        for (k, v) in headers {
            r = r.header(k, v);
        }
        r.json(body).send(self.addr).await
    }

    async fn stop(mut self) {
        if let Some(s) = self.stop.take() {
            let _ = s.send(());
        }
        let _ = self.task.await;
    }
}

const HI: &str = "{\"messages\": [{\"role\": \"user\", \"content\": \"hi\"}]}";

fn content(r: &console_testkit::raw::RawResponse) -> String {
    let v = console_pyjson::loads::loads_bytes(&r.body).unwrap_or(Value::Null);
    v["choices"][0]["message"]["content"]
        .as_str()
        .unwrap_or("")
        .to_owned()
}

async fn started(
    args: &[&str],
    env: &BTreeMap<String, String>,
) -> (Running, Vec<String>, LogCapture) {
    let (console, out, err) = console();
    match start(&opts(args), scripted_factory, &console, env).await {
        Ok(s) => (Running::of(s), out.lines(), err),
        Err(Exit(code)) => panic!("exit {code}: {:?} {:?}", out.lines(), err.lines()),
    }
}

#[tokio::test]
async fn the_default_start_prints_the_engine_line_then_the_ready_line() {
    let (server, lines, err) = started(&["--port", "0"], &BTreeMap::new()).await;
    let port = server.addr.port();
    assert_ne!(port, 0);
    assert_eq!(
        lines,
        vec![
            SYNTHETIC_ENGINE_LINE.to_owned(),
            format!("ready: http://127.0.0.1:{port}/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context 32768 tokens)"),
            format!("       open http://127.0.0.1:{port}/ in a browser to chat; close this window to stop the model"),
        ]
    );
    let r = server.post(&[], HI).await;
    assert_eq!(r.status, 200);
    // The donor's default script; with no reasoning parser in M1, all of it is content.
    assert_eq!(
        content(&r),
        "Thinking about it.</think>\n\nHello from the mock engine."
    );
    let v = console_pyjson::loads::loads_bytes(&r.body).unwrap_or(Value::Null);
    assert_eq!(v["model"], "pulsar-console-synthetic");
    assert!(err.lines().is_empty(), "{:?}", err.lines());
    server.stop().await;
}

#[tokio::test]
async fn scripts_rotate_and_the_last_one_repeats() {
    let (server, _, _) = started(
        &["--port=0", "--script", "one", "--script", "two"],
        &BTreeMap::new(),
    )
    .await;
    let mut got = Vec::new();
    for _ in 0..3 {
        got.push(content(&server.post(&[], HI).await));
    }
    assert_eq!(got, vec!["one", "two", "two"]);
    server.stop().await;
}

#[tokio::test]
async fn the_api_key_reaches_the_guard_and_the_ready_line() {
    let env = BTreeMap::from([(names::API_KEY.to_owned(), "k1".to_owned())]);
    let (server, lines, _) = started(&["--port", "0"], &env).await;
    assert!(lines
        .get(1)
        .is_some_and(|l| l.ends_with("context 32768 tokens, API key required)")));
    assert_eq!(server.post(&[], HI).await.status, 401);
    let r = server.post(&[("Authorization", "Bearer k1")], HI).await;
    assert_eq!(r.status, 200);
    server.stop().await;
    // The command line's key wins over the environment's.
    let (server, _, _) = started(&["--port", "0", "--api-key", "k2"], &env).await;
    let r = server.post(&[("Authorization", "Bearer k1")], HI).await;
    assert_eq!(r.status, 401);
    let r = server.post(&[("Authorization", "Bearer k2")], HI).await;
    assert_eq!(r.status, 200);
    server.stop().await;
}

#[tokio::test]
async fn the_transport_settings_come_from_the_environment() {
    // A body limit of 1 MiB: a larger body is answered 413 before it is read.
    let env = BTreeMap::from([(names::MAX_BODY_MIB.to_owned(), "1".to_owned())]);
    let (server, _, _) = started(&["--port", "0"], &env).await;
    let head = format!(
        "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n",
        2 << 20
    );
    let r = console_testkit::raw::exchange(server.addr, head.as_bytes()).await;
    assert_eq!(r.status, 413);
    assert!(r.text().contains("1 MiB"), "{}", r.text());
    server.stop().await;
}

fn write_config(dir: &TempDir, text: &str) -> String {
    let path = dir.path().join("pulsar-test.json");
    if let Err(e) = std::fs::write(&path, text) {
        panic!("write: {e}");
    }
    path.to_string_lossy().into_owned()
}

fn temp() -> TempDir {
    match TempDir::new("api08") {
        Ok(d) => d,
        Err(e) => panic!("temp dir: {e}"),
    }
}

#[tokio::test]
async fn the_run_config_gives_the_model_name_and_the_allowed_hosts() {
    let dir = temp();
    let config = write_config(
        &dir,
        "{\"model_name\": \"named-in-config\", \"allowed_hosts\": [\"box.lan\"]}",
    );
    let (server, _, _) = started(&["--port", "0", "--config", &config], &BTreeMap::new()).await;
    let r = server.post(&[], HI).await;
    let v = console_pyjson::loads::loads_bytes(&r.body).unwrap_or(Value::Null);
    assert_eq!(v["model"], "named-in-config");
    // `allowed_hosts` extends the loopback names (SEC-1.1); another name is refused.
    for (host, want) in [("box.lan", 200), ("evil.example", 403)] {
        let r = RawRequest::post("/v1/chat/completions")
            .header("Host", host)
            .json(HI)
            .send(server.addr)
            .await;
        assert_eq!(r.status, want, "{host}");
    }
    server.stop().await;
}

#[tokio::test]
async fn the_cors_origins_line_comes_before_the_engine_line() {
    let dir = temp();
    let config = write_config(
        &dir,
        "{\"cors_origins\": [\"http://127.0.0.1:8090\", \"http://a.lan:1\"]}",
    );
    let (server, lines, err) =
        started(&["--port", "0", "--config", &config], &BTreeMap::new()).await;
    let port = server.addr.port();
    assert_eq!(
        lines,
        vec![
            "[console] browser pages allowed to call /v1/* (CORS): http://127.0.0.1:8090, http://a.lan:1".to_owned(),
            SYNTHETIC_ENGINE_LINE.to_owned(),
            format!("ready: http://127.0.0.1:{port}/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context 32768 tokens)"),
            format!("       open http://127.0.0.1:{port}/ in a browser to chat; close this window to stop the model"),
        ]
    );
    assert!(err.lines().is_empty(), "{:?}", err.lines());
    server.stop().await;
}

async fn refused(args: &[&str], env: &BTreeMap<String, String>) -> (i32, Vec<String>, Vec<String>) {
    let (console, out, err) = console();
    match start(&opts(args), scripted_factory, &console, env).await {
        Ok(_) => panic!("{args:?} started"),
        Err(Exit(code)) => (code, out.lines(), err.lines()),
    }
}

#[tokio::test]
async fn an_allowed_hosts_entry_that_cannot_match_stops_the_start() {
    let dir = temp();
    let config = write_config(
        &dir,
        "{\"allowed_hosts\": [\"box.lan\", \"http://box.lan\"]}",
    );
    let (code, out, err) = refused(&["--port", "0", "--config", &config], &BTreeMap::new()).await;
    assert_eq!(code, 1);
    assert!(out.is_empty(), "{out:?}");
    assert_eq!(
        err,
        vec!["config: allowed_hosts: 'http://box.lan' is not a host name the server can match; the accepted forms are name, name:port, [v6] or [v6]:port".to_owned()]
    );
}

#[tokio::test]
async fn config_errors_stop_the_start() {
    let dir = temp();
    let config = write_config(&dir, "{\"cors_origins\": \"http://a:1\"}");
    let (code, out, err) = refused(&["--port", "0", "--config", &config], &BTreeMap::new()).await;
    assert_eq!(code, 1);
    assert!(out.is_empty());
    assert_eq!(err.len(), 1);
    assert!(
        err.first().is_some_and(|l| l.starts_with("config: ")),
        "{err:?}"
    );
    let missing = dir.path().join("absent.json");
    let missing = missing.to_string_lossy().into_owned();
    let (code, _, err) = refused(&["--port", "0", "--config", &missing], &BTreeMap::new()).await;
    assert_eq!(code, 1);
    assert!(
        err.first().is_some_and(|l| l.starts_with("config: ")),
        "{err:?}"
    );
}

#[tokio::test]
async fn a_port_in_use_is_the_usage_error() {
    let taken = match std::net::TcpListener::bind(("127.0.0.1", 0)) {
        Ok(l) => l,
        Err(e) => panic!("bind: {e}"),
    };
    let port = taken
        .local_addr()
        .map(|a| a.port())
        .unwrap_or(0)
        .to_string();
    let (code, out, err) = refused(&["--port", &port], &BTreeMap::new()).await;
    assert_eq!(code, 2);
    assert!(out.is_empty());
    assert_eq!(
        err,
        vec![
            "usage: pulsar-console [-h] [--config CONFIG] [--host HOST] [--script SCRIPT]".to_owned(),
            "                      [--port PORT] [--api-key API_KEY]".to_owned(),
            format!("pulsar-console: error: port {port} is already in use - is PulsarMLX Console (or another server) already running? Close it, or start this one with a different --port"),
        ]
    );
    drop(taken);
}

#[tokio::test]
async fn a_bad_engine_speed_stops_the_start() {
    let env = BTreeMap::from([(names::MOCK_TOK_S.to_owned(), "fast".to_owned())]);
    let (code, _, err) = refused(&["--port", "0"], &env).await;
    assert_eq!(code, 1);
    assert_eq!(
        err,
        vec![
            "[console] PULSAR_CONSOLE_MOCK_TOK_S: could not convert string to float: 'fast'"
                .to_owned()
        ]
    );
}

#[tokio::test]
async fn an_engine_that_is_not_synthetic_is_refused_in_process_too() {
    let (console, out, err) = console();
    let engine = NotSyntheticEngine::declaring("a real model");
    let probe = engine.clone();
    let r = start(
        &opts(&["--port", "0"]),
        move |_| Ok(Arc::new(engine)),
        &console,
        &BTreeMap::new(),
    )
    .await;
    assert!(matches!(r, Err(Exit(1))));
    assert_eq!(err.lines(), vec!["[console] refusing to start: engine scripted reports provenance not synthetic (declared \"a real model\"); this build serves synthetic engines only. See docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md".to_owned()]);
    assert!(out.lines().is_empty());
    // The refused engine was shut down and never asked to generate.
    assert_eq!(probe.generate_calls(), 0);
    assert_eq!(probe.shutdowns(), 1);
}

/// An engine factory that, when the turn driver's admission step starts it, records
/// whether anything accepts connections on the configured port, then starts the engine
/// that is not synthetic.
struct ProbingFactory {
    inner: NotSyntheticEngine,
    port: u16,
    accepted: Arc<std::sync::Mutex<Option<bool>>>,
}

impl EngineFactory for ProbingFactory {
    fn kind(&self) -> EngineKind {
        self.inner.kind()
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let up = std::net::TcpStream::connect(("127.0.0.1", self.port)).is_ok();
        *self
            .accepted
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner) = Some(up);
        self.inner.start(cfg)
    }
}

#[tokio::test]
async fn nothing_listens_while_the_refused_engine_is_admitted() {
    let port = match console_testkit::process::free_port() {
        Ok(p) => p,
        Err(e) => panic!("free port: {e}"),
    };
    let accepted = Arc::new(std::sync::Mutex::new(None));
    let factory = ProbingFactory {
        inner: NotSyntheticEngine::declaring("a real model"),
        port,
        accepted: Arc::clone(&accepted),
    };
    let (console, out, err) = console();
    let port_text = port.to_string();
    let r = start(
        &opts(&["--port", &port_text]),
        move |_| Ok(Arc::new(factory)),
        &console,
        &BTreeMap::new(),
    )
    .await;
    assert!(matches!(r, Err(Exit(1))));
    // The engine was started (and refused) while nothing accepted connections on the port:
    // the refusal comes before the listener is bound.
    assert_eq!(
        *accepted
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner),
        Some(false)
    );
    assert!(out.lines().is_empty(), "{:?}", out.lines());
    assert_eq!(err.lines().len(), 1, "{:?}", err.lines());
}

#[test]
fn a_refused_sampling_block_prints_its_notes_then_its_message() {
    let cfg =
        console_pyjson::loads::loads("{\"sampling\": {\"colour\": 1, \"temperature\": \"hot\"}}")
            .unwrap_or(Value::Null);
    let Some(map) = cfg.as_object() else {
        panic!("not an object");
    };
    let Err(e) = sampling_defaults_from_config(map) else {
        panic!("the block was accepted");
    };
    let (console, out, err) = console();
    pulsar_console::report_sampling_error(&console, &e);
    assert_eq!(out.lines(), e.notes().to_vec());
    assert!(!out.lines().is_empty());
    assert_eq!(err.lines(), vec![e.message().to_owned()]);
}
