use pulsar_serve_synthetic::runtime_adapter::{
    CancelProbe, GeneratedToken, RuntimeBackend, RuntimeSession, RuntimeSessionFactory, RuntimeStop,
};
use pulsar_serve_synthetic::{
    bind_loopback, serve, AppState, BackendDescriptor, BackendFailure, BackendMessage, BackendRole,
};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::sync::oneshot;

const MODEL: &str = "fixture-runtime";
const AUTH: &str = "fixture-runtime-auth-123456789";
#[derive(Clone, Copy)]
enum Mode {
    Stop,
    Length,
    WaitCancel,
    Uncooperative,
    DropBarrier,
    Fail,
    Panic,
    Replay,
    Many,
    Text,
    InvalidUtf8,
}
#[derive(Default)]
struct Spy {
    entered: AtomicBool,
    returned: AtomicBool,
    dropped: AtomicUsize,
    cancelled: AtomicBool,
    release: AtomicBool,
    prompt: Mutex<Vec<u32>>,
    ids: Mutex<Vec<(usize, u32)>>,
}
struct Factory {
    mode: Mode,
    spy: Arc<Spy>,
    refuse: bool,
}
impl RuntimeSessionFactory for Factory {
    fn create(&self) -> Result<Box<dyn RuntimeSession>, BackendFailure> {
        if self.refuse {
            return Err(BackendFailure::Generation);
        }
        Ok(Box::new(Session {
            mode: self.mode,
            spy: self.spy.clone(),
        }))
    }
}
struct Session {
    mode: Mode,
    spy: Arc<Spy>,
}
impl Drop for Session {
    fn drop(&mut self) {
        if matches!(self.mode, Mode::DropBarrier) && self.spy.entered.load(Ordering::SeqCst) {
            while !self.spy.release.load(Ordering::SeqCst) {
                std::thread::sleep(Duration::from_millis(1));
            }
        }
        self.spy.dropped.fetch_add(1, Ordering::SeqCst);
    }
}
impl RuntimeSession for Session {
    fn render(&mut self, messages: &[BackendMessage]) -> Result<Vec<u32>, BackendFailure> {
        if messages.len() != 1 || messages[0].role != BackendRole::User {
            return Err(BackendFailure::Generation);
        }
        // Fixture IDs with explicit role boundary, not text/message-length usage.
        Ok(vec![101, 201, 202, 301])
    }
    fn generate(
        &mut self,
        prompt: &[u32],
        maximum: u16,
        probe: &CancelProbe,
        emit: &mut dyn FnMut(GeneratedToken) -> Result<(), BackendFailure>,
    ) -> Result<RuntimeStop, BackendFailure> {
        *self.spy.prompt.lock().unwrap() = prompt.to_vec();
        self.spy.entered.store(true, Ordering::SeqCst);
        if matches!(self.mode, Mode::Panic) {
            panic!("controlled worker panic");
        }
        if matches!(self.mode, Mode::Fail) {
            return Err(BackendFailure::Generation);
        }
        if matches!(self.mode, Mode::WaitCancel | Mode::Uncooperative) {
            while !self.spy.release.load(Ordering::SeqCst) {
                if probe.is_cancelled() {
                    self.spy.cancelled.store(true, Ordering::SeqCst);
                    if matches!(self.mode, Mode::WaitCancel) {
                        break;
                    }
                }
                std::thread::sleep(Duration::from_millis(1));
            }
            self.spy.returned.store(true, Ordering::SeqCst);
            return Ok(RuntimeStop::Cancelled);
        }
        let limit = if matches!(self.mode, Mode::Many) {
            usize::from(maximum)
        } else {
            3
        };
        for sequence in 0..limit {
            let id = if sequence < 2 { 7 } else { 8 };
            self.spy.ids.lock().unwrap().push((sequence, id));
            let bytes = if matches!(self.mode, Mode::InvalidUtf8) {
                vec![0xff]
            } else if matches!(self.mode, Mode::Text) {
                vec![b'a' + sequence as u8]
            } else if matches!(self.mode, Mode::Many) {
                vec![b'x'; 1024]
            } else {
                match sequence {
                    0 => vec![0xf0],
                    1 => vec![0x9f, 0x9a],
                    _ => vec![0x80],
                }
            };
            emit(GeneratedToken {
                sequence: if matches!(self.mode, Mode::Replay) && sequence == 1 {
                    0
                } else {
                    sequence
                },
                id,
                bytes,
                stopping: false,
            })?;
        }
        if !matches!(self.mode, Mode::Length | Mode::Many) {
            self.spy.ids.lock().unwrap().push((limit, 99));
            emit(GeneratedToken {
                sequence: limit,
                id: 99,
                bytes: vec![],
                stopping: true,
            })?;
        }
        self.spy.returned.store(true, Ordering::SeqCst);
        Ok(if matches!(self.mode, Mode::Length | Mode::Many) {
            RuntimeStop::Length
        } else {
            RuntimeStop::Stop
        })
    }
}

struct Server {
    state: AppState,
    port: u16,
    shutdown: Option<oneshot::Sender<()>>,
    task: tokio::task::JoinHandle<std::io::Result<()>>,
    supervisor: Option<std::thread::JoinHandle<()>>,
    stop_supervisor: Option<std::sync::mpsc::Sender<()>>,
}
impl Server {
    async fn new(mode: Mode, refuse: bool) -> (Self, Arc<Spy>) {
        let spy = Arc::new(Spy::default());
        let backend = RuntimeBackend::new(
            BackendDescriptor {
                model_id: MODEL,
                owned_by: "fixture",
                capabilities: &["synthetic-only"],
            },
            Arc::new(Factory {
                mode,
                spy: spy.clone(),
                refuse,
            }),
        );
        let state = AppState::with_backend(AUTH.into(), Arc::new(backend)).unwrap();
        let listener = bind_loopback(0).await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let (tx, rx) = oneshot::channel();
        let app = state.clone();
        let task = tokio::spawn(serve(listener, app, async move {
            let _ = rx.await;
        }));
        let (stop_tx, stop_rx) = std::sync::mpsc::channel();
        let supervisor_spy = spy.clone();
        let cleanup = state.clone();
        // Independent outer supervisor always opens the barrier, including panic paths.
        let supervisor = std::thread::spawn(move || {
            let _ = stop_rx.recv_timeout(Duration::from_secs(8));
            supervisor_spy.release.store(true, Ordering::SeqCst);
            let end = std::time::Instant::now() + Duration::from_secs(2);
            while cleanup.metrics().backend_active > 0 && std::time::Instant::now() < end {
                cleanup.reap_cleanup();
                std::thread::sleep(Duration::from_millis(2));
            }
        });
        (
            Self {
                state,
                port,
                shutdown: Some(tx),
                task,
                supervisor: Some(supervisor),
                stop_supervisor: Some(stop_tx),
            },
            spy,
        )
    }
    async fn open(&self, stream: bool, role: &str, maximum: u16) -> TcpStream {
        let mut socket = TcpStream::connect(("127.0.0.1", self.port)).await.unwrap();
        let body=format!("{{\"model\":\"{MODEL}\",\"messages\":[{{\"role\":\"{role}\",\"content\":\"fixture\"}}],\"max_tokens\":{maximum},\"stream\":{stream}}}");
        let request=format!("POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {AUTH}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",self.port,body.len());
        socket.write_all(request.as_bytes()).await.unwrap();
        socket
    }
    async fn request(&self, stream: bool, role: &str, maximum: u16) -> String {
        let mut socket = self.open(stream, role, maximum).await;
        let mut bytes = vec![];
        tokio::time::timeout(Duration::from_secs(5), socket.read_to_end(&mut bytes))
            .await
            .unwrap()
            .unwrap();
        String::from_utf8(bytes).unwrap()
    }
    async fn finish(mut self, spy: &Spy) {
        spy.release.store(true, Ordering::SeqCst);
        if let Some(tx) = self.shutdown.take() {
            let _ = tx.send(());
        }
        let _ = tokio::time::timeout(Duration::from_secs(3), &mut self.task)
            .await
            .unwrap()
            .unwrap();
        let snapshot = self.state.drain_cleanup(Duration::from_secs(2)).await;
        assert_eq!(snapshot.backend_active, 0, "NO_FALSE_RESOURCE_ZERO");
        assert_eq!(snapshot.runtime_cleanup_pending, 0);
        assert_eq!(snapshot.stream_tasks_pending, 0);
        self.stop_supervisor.take().unwrap().send(()).unwrap();
        let supervisor = self.supervisor.take().unwrap();
        while !supervisor.is_finished() {
            tokio::time::sleep(Duration::from_millis(2)).await;
        }
        supervisor.join().unwrap();
    }
}
async fn wait(flag: &AtomicBool) {
    tokio::time::timeout(Duration::from_secs(1), async {
        while !flag.load(Ordering::SeqCst) {
            tokio::time::sleep(Duration::from_millis(2)).await;
        }
    })
    .await
    .unwrap();
}
async fn released(state: &AppState) {
    let snapshot = state.drain_cleanup(Duration::from_secs(2)).await;
    assert_eq!(snapshot.backend_active, 0);
    assert_eq!(snapshot.backend_finished, 1, "EXACT_ONCE_RELEASE");
    assert_eq!(snapshot.runtime_workers_joined, 1, "ACTUAL_HANDLE_JOINED");
}

#[tokio::test]
async fn multi_token_utf8_stop_and_exact_ids_usage() {
    let (server, spy) = Server::new(Mode::Stop, false).await;
    let response = server.request(false, "user", 3).await;
    assert!(response.starts_with("HTTP/1.1 200"));
    let body: serde_json::Value =
        serde_json::from_str(response.split("\r\n\r\n").nth(1).unwrap()).unwrap();
    assert_eq!(body["choices"][0]["message"]["content"], "🚀");
    assert_eq!(body["choices"][0]["finish_reason"], "stop");
    assert_eq!(
        body["usage"],
        serde_json::json!({"prompt_tokens":4,"completion_tokens":3,"total_tokens":7})
    );
    assert_eq!(*spy.prompt.lock().unwrap(), vec![101, 201, 202, 301]);
    assert_eq!(
        *spy.ids.lock().unwrap(),
        vec![(0, 7), (1, 7), (2, 8), (3, 99)]
    );
    assert_eq!(spy.dropped.load(Ordering::SeqCst), 1);
    released(&server.state).await;
    server.finish(&spy).await;
}
#[tokio::test]
async fn length_stream_has_one_role_and_terminal() {
    let (server, spy) = Server::new(Mode::Length, false).await;
    let response = server.request(true, "user", 3).await;
    assert_eq!(response.matches("\"role\":\"assistant\"").count(), 1);
    assert_eq!(response.matches("data: [DONE]").count(), 1);
    assert!(response.contains("\"finish_reason\":\"length\""));
    assert!(response.contains("🚀"));
    released(&server.state).await;
    server.finish(&spy).await;
}
#[tokio::test]
async fn ordered_multiple_deltas_and_invalid_utf8_fail_honestly() {
    let (server, spy) = Server::new(Mode::Text, false).await;
    let response = server.request(true, "user", 3).await;
    let a = response.find("\"content\":\"a\"").unwrap();
    let b = response.find("\"content\":\"b\"").unwrap();
    let c = response.find("\"content\":\"c\"").unwrap();
    assert!(a < b && b < c);
    assert_eq!(response.matches("data: [DONE]").count(), 1);
    released(&server.state).await;
    server.finish(&spy).await;
    let (server, spy) = Server::new(Mode::InvalidUtf8, false).await;
    let response = server.request(false, "user", 3).await;
    assert!(response.starts_with("HTTP/1.1 500"));
    released(&server.state).await;
    server.finish(&spy).await;
}
#[tokio::test]
async fn unsupported_history_and_prestart_refusal_launch_no_worker() {
    for refuse in [false, true] {
        let (server, spy) = Server::new(Mode::Stop, refuse).await;
        let response = server
            .request(false, if refuse { "user" } else { "assistant" }, 3)
            .await;
        assert!(response.starts_with("HTTP/1.1 500"));
        assert!(!spy.entered.load(Ordering::SeqCst));
        assert_eq!(server.state.metrics().runtime_workers_joined, 0);
        assert_eq!(server.state.metrics().backend_finished, 1);
        server.finish(&spy).await;
    }
}
#[tokio::test]
async fn producer_failure_and_panic_really_join() {
    for mode in [Mode::Fail, Mode::Panic] {
        let (server, spy) = Server::new(mode, false).await;
        let response = server.request(false, "user", 3).await;
        assert!(response.starts_with("HTTP/1.1 500"));
        assert_eq!(spy.dropped.load(Ordering::SeqCst), 1);
        released(&server.state).await;
        server.finish(&spy).await;
    }
}
#[tokio::test]
async fn duplicate_callback_ordinal_is_not_a_success() {
    let (server, spy) = Server::new(Mode::Replay, false).await;
    let response = server.request(false, "user", 3).await;
    assert!(response.starts_with("HTTP/1.1 500"));
    assert!(response.contains("backend_protocol_error"));
    released(&server.state).await;
    server.finish(&spy).await;
}
#[tokio::test]
async fn raw_sender_eof_does_not_release_a_live_destructor() {
    let (server, spy) = Server::new(Mode::DropBarrier, false).await;
    let mut socket = server.open(false, "user", 3).await;
    wait(&spy.returned).await;
    tokio::time::sleep(Duration::from_millis(40)).await;
    assert_eq!(spy.dropped.load(Ordering::SeqCst), 0);
    let busy = server.request(false, "user", 3).await;
    assert!(busy.starts_with("HTTP/1.1 429"), "PERMIT_HELD_ON_EOF");
    assert_eq!(server.state.metrics().runtime_workers_joined, 0);
    spy.release.store(true, Ordering::SeqCst);
    let mut bytes = vec![];
    tokio::time::timeout(Duration::from_secs(2), socket.read_to_end(&mut bytes))
        .await
        .unwrap()
        .unwrap();
    assert!(bytes.starts_with(b"HTTP/1.1 200"));
    released(&server.state).await;
    server.finish(&spy).await;
}
#[tokio::test]
async fn client_disconnect_requests_cancel_and_joins() {
    let (server, spy) = Server::new(Mode::WaitCancel, false).await;
    let mut socket = server.open(true, "user", 3).await;
    let mut bytes = [0; 1024];
    let _ = socket.read(&mut bytes).await.unwrap();
    wait(&spy.entered).await;
    drop(socket);
    wait(&spy.cancelled).await;
    released(&server.state).await;
    assert_eq!(spy.dropped.load(Ordering::SeqCst), 1);
    server.finish(&spy).await;
}
#[tokio::test]
async fn timeout_holds_capacity_until_uncooperative_worker_exits() {
    let (server, spy) = Server::new(Mode::Uncooperative, false).await;
    let response = server.request(false, "user", 3).await;
    assert!(response.starts_with("HTTP/1.1 504"));
    wait(&spy.cancelled).await;
    let m = server.state.metrics();
    assert_eq!(m.backend_active, 1);
    assert_eq!(m.backend_finished, 0);
    assert_eq!(m.runtime_cleanup_pending, 1);
    let busy = server.request(false, "user", 3).await;
    assert!(
        busy.starts_with("HTTP/1.1 429"),
        "PERMIT_HELD_AFTER_ASYNC_DROP"
    );
    spy.release.store(true, Ordering::SeqCst);
    released(&server.state).await;
    assert_eq!(spy.dropped.load(Ordering::SeqCst), 1);
    server.finish(&spy).await;
}
#[tokio::test]
async fn shutdown_reports_incomplete_then_owned_drain_joins() {
    let (mut server, spy) = Server::new(Mode::Uncooperative, false).await;
    let _socket = server.open(true, "user", 3).await;
    wait(&spy.entered).await;
    server.shutdown.take().unwrap().send(()).unwrap();
    let result = tokio::time::timeout(Duration::from_secs(1), &mut server.task)
        .await
        .unwrap()
        .unwrap();
    assert_eq!(result.unwrap_err().kind(), std::io::ErrorKind::TimedOut);
    let snapshot = server.state.drain_cleanup(Duration::from_millis(20)).await;
    assert_eq!(snapshot.backend_active, 1, "TRUTHFUL_INCOMPLETE_SHUTDOWN");
    assert_eq!(snapshot.runtime_workers_joined, 0);
    spy.release.store(true, Ordering::SeqCst);
    released(&server.state).await;
    // Task already joined: finish supervisor directly.
    server.stop_supervisor.take().unwrap().send(()).unwrap();
    let supervisor = server.supervisor.take().unwrap();
    while !supervisor.is_finished() {
        tokio::time::sleep(Duration::from_millis(2)).await;
    }
    supervisor.join().unwrap();
}
#[tokio::test]
async fn cooperative_shutdown_drains_stream_task_and_worker() {
    let (mut server, spy) = Server::new(Mode::WaitCancel, false).await;
    let _socket = server.open(true, "user", 3).await;
    wait(&spy.entered).await;
    server.shutdown.take().unwrap().send(()).unwrap();
    tokio::time::timeout(Duration::from_secs(1), &mut server.task)
        .await
        .unwrap()
        .unwrap()
        .unwrap();
    wait(&spy.cancelled).await;
    released(&server.state).await;
    assert_eq!(server.state.metrics().stream_tasks_pending, 0);
    server.stop_supervisor.take().unwrap().send(()).unwrap();
    let supervisor = server.supervisor.take().unwrap();
    while !supervisor.is_finished() {
        tokio::time::sleep(Duration::from_millis(2)).await;
    }
    supervisor.join().unwrap();
}
#[tokio::test]
async fn bounded_large_stream_disconnect_reaps_backpressured_worker() {
    let (server, spy) = Server::new(Mode::Many, false).await;
    let mut socket = server.open(true, "user", 16).await;
    let mut bytes = [0; 128];
    let _ = socket.read(&mut bytes).await.unwrap();
    drop(socket);
    released(&server.state).await;
    server.finish(&spy).await;
}
