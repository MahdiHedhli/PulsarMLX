//! The `pulsar-console` binary as a spawned process: the ready line under `--port 0`, the
//! port-in-use error, usage errors and help, and one streamed chat completion end to end
//! over a real socket. Every process is killed and reaped by the end of its test, also when
//! the test fails (the test kit's `Proc` on drop, `Exited::run` on its deadline).
//!
//! The binary is the one cargo builds for these tests; built alone (`cargo build --locked
//! -p pulsar-console`) the package leaves the `test-support` feature of `console-engine`
//! out, so the shipped binary holds no test double.

use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::process::{Command, ExitStatus, Stdio};
use std::time::{Duration, Instant};

use console_testkit::process::{parse_ready, spawn_locked, Proc};

/// The binary under test.
const BIN: &str = env!("CARGO_BIN_EXE_pulsar-console");

/// A generous bound for a process to start, answer or end.
const DEADLINE: Duration = Duration::from_secs(20);

/// The server's command with a clean environment (no `PULSAR_CONSOLE_*` setting of the
/// shell running the tests reaches it) and standard input closed.
fn command(args: &[&str]) -> Command {
    let mut c = Command::new(BIN);
    c.args(args).env_clear().stdin(Stdio::null());
    c
}

/// A process run to its end: its status and both streams.
struct Exited {
    status: ExitStatus,
    stdout: String,
    stderr: String,
}

impl Exited {
    /// Runs `command` until it exits; kills and reaps it, then fails, if it is still
    /// running after the deadline.
    fn run(mut command: Command) -> Self {
        command.stdout(Stdio::piped()).stderr(Stdio::piped());
        // Through the kit's spawn lock, as `Proc::spawn` in the other tests of this binary:
        // a child started without it can inherit a pipe end of another test's child.
        let mut child = match spawn_locked(&mut command) {
            Ok(c) => c,
            Err(e) => panic!("spawn: {e}"),
        };
        let read = |pipe: Option<Box<dyn Read + Send>>| {
            std::thread::spawn(move || {
                let mut text = String::new();
                if let Some(mut p) = pipe {
                    let _ = p.read_to_string(&mut text);
                }
                text
            })
        };
        let out = read(
            child
                .stdout
                .take()
                .map(|p| Box::new(p) as Box<dyn Read + Send>),
        );
        let err = read(
            child
                .stderr
                .take()
                .map(|p| Box::new(p) as Box<dyn Read + Send>),
        );
        let started = Instant::now();
        let status = loop {
            match child.try_wait() {
                Ok(Some(status)) => break status,
                Ok(None) if started.elapsed() < DEADLINE => {
                    std::thread::sleep(Duration::from_millis(10));
                }
                _ => {
                    let _ = child.kill();
                    let _ = child.wait();
                    panic!("the process did not exit within {DEADLINE:?}");
                }
            }
        };
        Self {
            status,
            stdout: out.join().unwrap_or_default(),
            stderr: err.join().unwrap_or_default(),
        }
    }
}

/// The usage block argparse prints for this command line, at the default width of 80.
const USAGE: &str = "usage: pulsar-console [-h] [--config CONFIG] [--host HOST] [--script SCRIPT]\n                      [--port PORT] [--api-key API_KEY]\n";

#[test]
fn the_ready_line_names_the_bound_port_under_port_zero() {
    let mut p = match Proc::spawn(command(&["--port", "0"])) {
        Ok(p) => p,
        Err(e) => panic!("spawn: {e}"),
    };
    let Some(ready) = p.wait_ready(DEADLINE) else {
        panic!("no ready line: {:?}", p.seen());
    };
    // Proposal P-25: the port the operating system bound, never 0.
    assert_ne!(ready.port, 0);
    assert_eq!(ready.host, "127.0.0.1");
    assert_eq!(
        ready.line,
        format!(
            "ready: http://127.0.0.1:{}/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context 32768 tokens)",
            ready.port
        )
    );
    // Lead decision LD46: the synthetic engine is said before the ready line.
    assert_eq!(
        p.seen(),
        vec![
            "[console] engine: scripted, synthetic provenance - no real model is served".to_owned(),
            ready.line.clone(),
        ]
    );
    assert!(p.until("open http://127.0.0.1:", DEADLINE));
    assert!(
        matches!(p.try_status(), Ok(None)),
        "the server keeps running"
    );
    let status = p.close();
    assert!(status.is_ok());
}

#[test]
fn a_port_in_use_is_a_usage_error_before_anything_starts() {
    let taken = match TcpListener::bind(("127.0.0.1", 0)) {
        Ok(l) => l,
        Err(e) => panic!("bind: {e}"),
    };
    let port = taken.local_addr().map(|a| a.port()).unwrap_or(0);
    let out = Exited::run(command(&["--port", &port.to_string()]));
    assert_eq!(out.status.code(), Some(2));
    assert_eq!(out.stdout, "");
    assert_eq!(
        out.stderr,
        format!(
            "{USAGE}pulsar-console: error: port {port} is already in use - is PulsarMLX Console (or another server) already running? Close it, or start this one with a different --port\n"
        )
    );
    drop(taken);
}

#[test]
fn usage_errors_exit_2_and_help_exits_0() {
    let out = Exited::run(command(&["--port", "x"]));
    assert_eq!(out.status.code(), Some(2));
    assert_eq!(
        out.stderr,
        format!("{USAGE}pulsar-console: error: argument --port: invalid int value: 'x'\n")
    );
    let out = Exited::run(command(&["--gpu", "0"]));
    assert_eq!(out.status.code(), Some(2));
    assert!(out
        .stderr
        .ends_with("pulsar-console: error: unrecognized arguments: --gpu 0\n"));
    let out = Exited::run(command(&["--help"]));
    assert_eq!(out.status.code(), Some(0));
    assert!(out.stdout.starts_with(USAGE), "{}", out.stdout);
    assert_eq!(out.stderr, "");
    // A port no socket takes: the donor's uncaught OverflowError, exit 1.
    let out = Exited::run(command(&["--port", "70000"]));
    assert_eq!(out.status.code(), Some(1));
    assert_eq!(out.stderr, "OverflowError: bind(): port must be 0-65535.\n");
}

#[test]
fn a_streamed_answer_end_to_end_over_a_real_socket() {
    let mut p = match Proc::spawn(command(&["--port=0", "--script", "Hi!"])) {
        Ok(p) => p,
        Err(e) => panic!("spawn: {e}"),
    };
    let Some(ready) = p.wait_ready(DEADLINE) else {
        panic!("no ready line: {:?}", p.seen());
    };
    let body = "{\"model\": \"any\", \"stream\": true, \"messages\": [{\"role\": \"user\", \"content\": \"hi\"}]}";
    let request = format!(
        "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",
        ready.port,
        body.len()
    );
    let mut stream = match TcpStream::connect(("127.0.0.1", ready.port)) {
        Ok(s) => s,
        Err(e) => panic!("connect: {e}"),
    };
    let _ = stream.set_read_timeout(Some(DEADLINE));
    if let Err(e) = stream.write_all(request.as_bytes()) {
        panic!("write: {e}");
    }
    let mut raw = Vec::new();
    if let Err(e) = stream.read_to_end(&mut raw) {
        panic!("read: {e}");
    }
    let text = String::from_utf8_lossy(&raw).into_owned();
    let Some((head, frames)) = text.split_once("\r\n\r\n") else {
        panic!("no head: {text}");
    };
    assert!(head.starts_with("HTTP/1.0 200 OK\r\n"), "{head}");
    assert!(
        head.contains("\r\nContent-Type: text/event-stream\r\n"),
        "{head}"
    );
    let datas: Vec<&str> = frames.split("\n\n").filter(|f| !f.is_empty()).collect();
    assert_eq!(datas.last().copied(), Some("data: [DONE]"));
    let chunks: Vec<serde_json::Value> = datas
        .iter()
        .filter(|f| **f != "data: [DONE]")
        .map(|f| {
            let json = f.strip_prefix("data: ").unwrap_or("");
            console_pyjson::loads::loads(json).unwrap_or(serde_json::Value::Null)
        })
        .collect();
    let id = chunks.first().map(|c| c["id"].clone());
    let content: String = chunks
        .iter()
        .filter_map(|c| c["choices"][0]["delta"]["content"].as_str())
        .collect();
    assert_eq!(content, "Hi!");
    for c in &chunks {
        assert_eq!(c["model"], "pulsar-console-synthetic");
        assert_eq!(c["object"], "chat.completion.chunk");
        assert_eq!(Some(c["id"].clone()), id);
    }
    let id = id
        .and_then(|v| v.as_str().map(str::to_owned))
        .unwrap_or_default();
    assert!(id.starts_with("chatcmpl-") && id.len() == 33, "{id}");
    let Some(last) = chunks.last() else {
        panic!("no chunk");
    };
    assert_eq!(last["choices"][0]["finish_reason"], "stop");
    assert_eq!(last["usage"]["completion_tokens"], 4);
    // Nothing went to standard error, and the ready line was the only one parsed as such.
    assert!(p.seen().iter().filter(|l| parse_ready(l).is_some()).count() == 1);
    let status = p.close();
    assert!(status.is_ok());
}
