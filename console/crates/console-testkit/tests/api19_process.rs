//! Tests of the test kit's process helper (work package API-19) with `/bin/sh` scripts
//! standing in for the server, whose binary (API-08) and fake engines (ENG-05) do not
//! exist yet: waiting for a line, the ready line, both output streams, a signal and the
//! exit status, the end of standard input, the kill on drop, and the fake run config with
//! a tokenizer folder the tokenizer crate loads.
//!
//! These are tests of the kit itself, not re-expressions of donor methods. Unix only: the
//! stand-in is a shell script and the signals are POSIX ones.
#![cfg(unix)]

use std::os::unix::process::ExitStatusExt;
use std::process::Command;
use std::time::Duration;

use console_testkit::process::{
    fake_config, free_port, Proc, ServerCommand, FAKE_CONFIG_NAME, FAKE_IM_END_ID,
    FAKE_THINK_END_ID,
};
use console_testkit::server::TempDir;
use serde_json::Value;

const WAIT: Duration = Duration::from_secs(20);

fn sh(script: &str) -> Proc {
    let mut command = Command::new("/bin/sh");
    command.arg("-c").arg(script);
    match Proc::spawn(command) {
        Ok(p) => p,
        Err(e) => panic!("spawn /bin/sh: {e}"),
    }
}

#[test]
fn the_ready_line_and_a_signal() {
    let mut p = sh("echo starting; echo warming 1>&2; \
         trap 'echo got-term; exit 3' TERM; \
         echo 'ready: http://127.0.0.1:4321/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context 4096 tokens)'; \
         while :; do sleep 0.05; done");
    let ready = p.wait_ready(WAIT).expect("a ready line");
    assert_eq!((ready.host.as_str(), ready.port), ("127.0.0.1", 4321));
    assert!(p.seen().contains(&"starting".to_owned()));
    assert!(p.try_status().expect("status").is_none(), "still running");
    p.signal(libc::SIGTERM).expect("signal");
    let status = p.wait_exit(WAIT).expect("wait").expect("ended");
    assert_eq!(status.code(), Some(3));
    let rest = p.rest(WAIT);
    assert!(rest.contains("got-term"), "{rest}");
    assert!(
        rest.contains("warming"),
        "standard error is read too: {rest}"
    );
    assert!(
        p.signal(libc::SIGTERM).is_err(),
        "no signal to a reaped child"
    );
}

#[test]
fn until_gives_up_at_the_end_of_the_output() {
    let mut p = sh("echo one; echo two");
    assert!(p.until("two", WAIT));
    assert!(!p.until("three", WAIT), "the output ended without it");
    assert_eq!(p.seen(), vec!["one".to_owned(), "two".to_owned()]);
    let status = p.wait_exit(WAIT).expect("wait").expect("ended");
    assert!(status.success());
}

#[test]
fn until_gives_up_at_its_deadline() {
    let mut p = sh("echo early; sleep 30");
    assert!(p.until("early", WAIT));
    assert!(!p.until("never", Duration::from_millis(200)));
    let status = p.close().expect("closed");
    assert_eq!(
        status.signal(),
        Some(libc::SIGKILL),
        "close kills a running child"
    );
}

#[test]
fn closing_standard_input_ends_a_reader() {
    let mut p = sh("cat; echo stdin-closed");
    {
        use std::io::Write;
        let stdin = p.stdin().expect("open");
        stdin.write_all(b"echoed\n").expect("write");
        stdin.flush().expect("flush");
    }
    assert!(p.until("echoed", WAIT));
    p.close_stdin();
    assert!(p.until("stdin-closed", WAIT));
    assert!(p.wait_exit(WAIT).expect("wait").is_some());
}

#[test]
fn a_dropped_proc_leaves_no_process() {
    let p = sh("sleep 30");
    let pid = libc::pid_t::try_from(p.pid()).expect("pid");
    drop(p);
    // SAFETY: signal 0 only checks whether the pid exists; it touches no memory.
    let alive = unsafe { libc::kill(pid, 0) } == 0;
    assert!(!alive, "the child was killed and reaped");
}

#[test]
fn the_fake_config_and_its_tokenizer() {
    let dir = TempDir::new("fake-config").expect("temp dir");
    let exe = dir.path().join("fake-engine");
    let cfg = fake_config(dir.path(), &exe).expect("written");
    assert_eq!(cfg, dir.path().join(FAKE_CONFIG_NAME));
    let text = std::fs::read_to_string(&cfg).expect("read");
    let v: Value = serde_json::from_str(&text).expect("JSON");
    let keys: Vec<&str> = v
        .as_object()
        .map(|m| m.keys().map(String::as_str).collect())
        .unwrap_or_default();
    assert_eq!(keys, vec!["exe", "args", "tokenizer", "model_name", "log"]);
    assert_eq!(v["exe"].as_str(), exe.to_str());
    assert_eq!(v["args"], serde_json::json!(["1"]));
    assert_eq!(v["model_name"], "fake");
    assert!(
        text.contains("\", \""),
        "written as json.dumps writes it: {text}"
    );
    let tok_dir = dir.path().join("tokenizer");
    let tok = console_tokenizer::pack_dir::from_dir(&tok_dir).expect("the tokenizer loads");
    assert_eq!(tok.n_vocab(), 258);
    assert_eq!(tok.id_of("<|im_end|>"), Some(FAKE_IM_END_ID));
    assert_eq!(tok.id_of("</think>"), Some(FAKE_THINK_END_ID));
    assert_eq!(tok.id_of("\u{120}"), Some(32), "GPT-2's space");
}

#[test]
fn a_server_command_for_the_seam() {
    let port = free_port().expect("port");
    let c = ServerCommand::new(std::path::Path::new("/bin/echo"), port)
        .config(std::path::Path::new("cfg.json"));
    let mut p = Proc::spawn(c.command()).expect("spawn");
    assert!(p.until(&format!("--config cfg.json --port {port}"), WAIT));
}
