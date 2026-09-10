#![cfg(unix)]

use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant, SystemTime};

fn exchange(port: u16, request: &str) -> String {
    let mut stream = TcpStream::connect(("127.0.0.1", port)).expect("connect request");
    stream
        .set_read_timeout(Some(Duration::from_secs(2)))
        .expect("read timeout");
    stream.write_all(request.as_bytes()).expect("write request");
    let mut response = String::new();
    stream.read_to_string(&mut response).expect("read response");
    response
}

#[test]
fn fresh_process_serves_loopback_and_shuts_down_without_content_logs() {
    let unique = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    let root = std::env::temp_dir().join(format!(
        "pulsar-synthetic-process-{}-{unique}",
        std::process::id()
    ));
    fs::create_dir(&root).expect("create root");
    fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).expect("root mode");
    let token_path = root.join("token");
    let token = format!("synthetic-runtime-token-{}-{unique}", std::process::id());
    let mut token_file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&token_path)
        .expect("create token file");
    token_file.write_all(token.as_bytes()).expect("write token");
    drop(token_file);

    let probe = TcpListener::bind("127.0.0.1:0").expect("reserve port");
    let port = probe.local_addr().expect("probe address").port();
    drop(probe);
    let mut child = Command::new(env!("CARGO_BIN_EXE_pulsar-serve-synthetic"))
        .args([
            "--token-file",
            token_path.to_str().expect("token path"),
            "--port",
            &port.to_string(),
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("spawn server");

    let start = Instant::now();
    let stream = loop {
        match TcpStream::connect(("127.0.0.1", port)) {
            Ok(stream) => break stream,
            Err(_) if start.elapsed() < Duration::from_secs(3) => {
                thread::sleep(Duration::from_millis(20))
            }
            Err(error) => panic!("server did not start: {error}"),
        }
    };
    drop(stream);

    let health = exchange(
        port,
        &format!("GET /health HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n"),
    );
    assert!(health.starts_with("HTTP/1.1 200"));
    assert!(health.contains("\"status\":\"ok\""));

    let models_request = format!(
        "GET /v1/models HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAuthorization: Bearer {token}\r\nConnection: close\r\n\r\n"
    );
    let models = exchange(port, &models_request);
    assert!(models.starts_with("HTTP/1.1 200"));
    assert!(models.contains("pulsarmlx-synthetic-v1"));

    let body = r#"{"model":"pulsarmlx-synthetic-v1","messages":[{"role":"user","content":"fresh-process-input"}]}"#;
    let completion_request = format!(
        "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAuthorization: Bearer {token}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    let completion = exchange(port, &completion_request);
    assert!(completion.starts_with("HTTP/1.1 200"));
    assert!(completion.contains("SYNTHETIC_OK: café 🚀"));

    let signal_result = unsafe { libc::kill(child.id() as i32, libc::SIGINT) };
    assert_eq!(signal_result, 0, "send SIGINT");
    let deadline = Instant::now() + Duration::from_secs(3);
    let status = loop {
        if let Some(status) = child.try_wait().expect("wait") {
            break status;
        }
        assert!(Instant::now() < deadline, "server did not shut down");
        thread::sleep(Duration::from_millis(20));
    };
    assert!(status.success());

    let mut stdout = String::new();
    child
        .stdout
        .take()
        .expect("stdout")
        .read_to_string(&mut stdout)
        .expect("read stdout");
    let mut stderr = String::new();
    child
        .stderr
        .take()
        .expect("stderr")
        .read_to_string(&mut stderr)
        .expect("read stderr");
    assert!(!stdout.contains(&token));
    assert!(!stderr.contains(&token));
    assert!(!stdout.contains("pulsarmlx-synthetic-v1"));
    assert!(!stderr.contains("pulsarmlx-synthetic-v1"));
    assert!(!stdout.contains("fresh-process-input"));
    assert!(!stderr.contains("fresh-process-input"));
    assert!(!stdout.contains("SYNTHETIC_OK"));
    assert!(!stderr.contains("SYNTHETIC_OK"));

    fs::remove_file(token_path).expect("remove token");
    fs::remove_dir(root).expect("remove root");
}
