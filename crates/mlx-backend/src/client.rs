//! Supervised lifecycle for one persistent MLX worker process.

use crate::protocol::{
    parse_hello_line, parse_response_line, parse_synthetic_moe_result, parse_tensor_fixture_result,
    HelloExpectation, ProtocolLimits, RequestEnvelope, SyntheticMoeRequest, SyntheticMoeResult,
    TensorFixtureRequest, TensorFixtureResult, WorkerError, WorkerErrorKind, WorkerHello,
    MAX_RESPONSE_BYTES, PROTOCOL_VERSION,
};
use serde_json::{Map, Value};
use std::ffi::OsString;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Command, ExitStatus, Stdio};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, SyncSender, TryRecvError};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

const DEFAULT_WORKER_VERSION: &str = env!("CARGO_PKG_VERSION");
const DEFAULT_MLX_VERSION: &str = "0.32.0";
const READER_CHANNEL_CAPACITY: usize = 1;
const READER_JOIN_BUDGET: Duration = Duration::from_millis(50);
const CHILD_STATUS_POLL_INTERVAL: Duration = Duration::from_millis(2);

/// Deadlines for startup negotiation, ordinary requests, and shutdown.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct WorkerTimeouts {
    startup: Duration,
    request: Duration,
    shutdown: Duration,
}

impl WorkerTimeouts {
    pub const fn new(startup: Duration, request: Duration, shutdown: Duration) -> Self {
        Self {
            startup,
            request,
            shutdown,
        }
    }

    pub const fn startup(&self) -> Duration {
        self.startup
    }

    pub const fn request(&self) -> Duration {
        self.request
    }

    pub const fn shutdown(&self) -> Duration {
        self.shutdown
    }
}

impl Default for WorkerTimeouts {
    fn default() -> Self {
        Self::new(
            Duration::from_secs(10),
            Duration::from_secs(30),
            Duration::from_secs(5),
        )
    }
}

/// Process and protocol pins used to create one worker context.
#[derive(Debug, Clone)]
pub struct WorkerConfig {
    program: PathBuf,
    args: Vec<OsString>,
    expected_protocol: u32,
    expected_worker_version: String,
    expected_mlx_version: String,
    timeouts: WorkerTimeouts,
    environment: Vec<(OsString, OsString)>,
    current_dir: Option<PathBuf>,
}

impl WorkerConfig {
    pub fn new(program: PathBuf, args: Vec<OsString>) -> Self {
        Self {
            program,
            args,
            expected_protocol: PROTOCOL_VERSION,
            expected_worker_version: DEFAULT_WORKER_VERSION.to_owned(),
            expected_mlx_version: DEFAULT_MLX_VERSION.to_owned(),
            timeouts: WorkerTimeouts::default(),
            environment: Vec::new(),
            current_dir: None,
        }
    }

    pub fn with_expected_protocol(mut self, protocol: u32) -> Self {
        self.expected_protocol = protocol;
        self
    }

    pub fn with_expected_worker_version(mut self, version: impl Into<String>) -> Self {
        self.expected_worker_version = version.into();
        self
    }

    pub fn with_expected_mlx_version(mut self, version: impl Into<String>) -> Self {
        self.expected_mlx_version = version.into();
        self
    }

    pub fn with_timeouts(mut self, timeouts: WorkerTimeouts) -> Self {
        self.timeouts = timeouts;
        self
    }

    pub fn with_env(mut self, key: impl Into<OsString>, value: impl Into<OsString>) -> Self {
        self.environment.push((key.into(), value.into()));
        self
    }

    pub fn with_current_dir(mut self, current_dir: impl Into<PathBuf>) -> Self {
        self.current_dir = Some(current_dir.into());
        self
    }

    pub fn program(&self) -> &Path {
        &self.program
    }

    pub fn args(&self) -> &[OsString] {
        &self.args
    }

    pub fn timeouts(&self) -> WorkerTimeouts {
        self.timeouts
    }
}

/// Result of a health request admitted by a negotiated worker.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct HealthReport {
    request_id: u64,
    ready: bool,
}

impl HealthReport {
    pub fn request_id(&self) -> u64 {
        self.request_id
    }

    pub fn ready(&self) -> bool {
        self.ready
    }
}

/// How worker cleanup completed.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CleanupOutcome {
    Graceful,
    ForcedTermination,
    Failed,
}

/// Bounded worker cleanup record.
#[derive(Debug, Clone, PartialEq)]
pub struct CleanupReport {
    outcome: CleanupOutcome,
    exit_code: Option<i32>,
    error: Option<WorkerError>,
}

impl CleanupReport {
    pub fn outcome(&self) -> CleanupOutcome {
        self.outcome
    }

    pub fn exit_code(&self) -> Option<i32> {
        self.exit_code
    }

    pub fn error(&self) -> Option<&WorkerError> {
        self.error.as_ref()
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum WorkerState {
    Negotiating,
    Ready,
    Failed,
    ShuttingDown,
    Stopped,
}

#[derive(Debug)]
enum ReaderEvent {
    Line(Vec<u8>),
    MessageTooLarge,
    Io,
    Eof,
}

/// A single persistent worker supervised for one backend context.
pub struct WorkerClient {
    child: Child,
    stdin: Option<ChildStdin>,
    reader: Receiver<ReaderEvent>,
    reader_handle: Option<JoinHandle<()>>,
    hello: Option<WorkerHello>,
    limits: ProtocolLimits,
    timeouts: WorkerTimeouts,
    next_request_id: u64,
    state: WorkerState,
}

impl WorkerClient {
    /// Spawn exactly one child and negotiate its unsolicited hello before
    /// admitting requests.
    pub fn spawn(config: WorkerConfig) -> Result<Self, WorkerError> {
        let expectation = HelloExpectation::new(
            config.expected_protocol,
            config.expected_worker_version,
            config.expected_mlx_version,
        )?;

        let mut command = Command::new(&config.program);
        command
            .args(&config.args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit());
        for (key, value) in &config.environment {
            command.env(key, value);
        }
        if let Some(current_dir) = &config.current_dir {
            command.current_dir(current_dir);
        }

        let mut child = command.spawn().map_err(|error| {
            WorkerError::new(
                WorkerErrorKind::Spawn,
                format!("worker process could not be spawned: {error}"),
            )
        })?;
        let stdin = match child.stdin.take() {
            Some(stdin) => stdin,
            None => {
                terminate_unowned_child(&mut child);
                return Err(WorkerError::new(
                    WorkerErrorKind::Io,
                    "worker stdin pipe was not created",
                ));
            }
        };
        let stdout = match child.stdout.take() {
            Some(stdout) => stdout,
            None => {
                terminate_unowned_child(&mut child);
                return Err(WorkerError::new(
                    WorkerErrorKind::Io,
                    "worker stdout pipe was not created",
                ));
            }
        };
        let (reader, reader_handle) = spawn_stdout_reader(stdout);

        let mut client = Self {
            child,
            stdin: Some(stdin),
            reader,
            reader_handle: Some(reader_handle),
            hello: None,
            limits: ProtocolLimits::default(),
            timeouts: config.timeouts,
            next_request_id: 1,
            state: WorkerState::Negotiating,
        };

        let line = client.receive_line(config.timeouts.startup)?;
        let hello = parse_hello_line(&line, &expectation, &client.limits)?;
        let limits = client.limits.negotiated(hello.limits())?;
        client.hello = Some(hello);
        client.limits = limits;
        client.state = WorkerState::Ready;
        Ok(client)
    }

    pub fn hello(&self) -> &WorkerHello {
        self.hello
            .as_ref()
            .expect("a constructed WorkerClient has negotiated hello metadata")
    }

    pub fn health(&mut self) -> Result<HealthReport, WorkerError> {
        let (request_id, result) =
            self.request_with_timeout("health", Map::new(), self.timeouts.request)?;
        let ready = result.get("ready").and_then(Value::as_bool).ok_or_else(|| {
            WorkerError::new(
                WorkerErrorKind::Protocol,
                "worker health result omits a boolean ready field",
            )
        });
        match ready {
            Ok(ready) => Ok(HealthReport { request_id, ready }),
            Err(error) => {
                self.state = WorkerState::Failed;
                Err(error)
            }
        }
    }

    /// Execute one bounded protocol operation using the negotiated limits and
    /// the monotonically increasing request-ID stream.
    pub fn request_operation(
        &mut self,
        operation: &str,
        params: Map<String, Value>,
    ) -> Result<(u64, Value), WorkerError> {
        self.request_with_timeout(operation, params, self.timeouts.request)
    }

    /// Execute one committed fixture through the negotiated control-only
    /// protocol and validate its bounded readback before exposing it.
    pub fn run_fixture(
        &mut self,
        request: &TensorFixtureRequest,
    ) -> Result<TensorFixtureResult, WorkerError> {
        if !self
            .hello()
            .capabilities()
            .operations()
            .iter()
            .any(|operation| operation == "run_fixture")
        {
            return Err(WorkerError::new(
                WorkerErrorKind::Protocol,
                "negotiated worker does not advertise fixture execution",
            ));
        }

        let max_fixture_elements = self.hello().limits().max_fixture_elements();
        let (_, value) = self.request_with_timeout(
            "run_fixture",
            request.protocol_params(),
            self.timeouts.request,
        )?;
        match parse_tensor_fixture_result(value, request, max_fixture_elements) {
            Ok(result) => Ok(result),
            Err(error) => {
                self.state = WorkerState::Failed;
                Err(error)
            }
        }
    }

    /// Execute the committed synthetic routed-MoE case through one bounded,
    /// control-only request and validate the complete evidence response.
    pub fn run_synthetic_moe(
        &mut self,
        request: &SyntheticMoeRequest,
    ) -> Result<SyntheticMoeResult, WorkerError> {
        if !self
            .hello()
            .capabilities()
            .operations()
            .iter()
            .any(|operation| operation == "run_synthetic_moe")
        {
            return Err(WorkerError::new(
                WorkerErrorKind::Protocol,
                "negotiated worker does not advertise synthetic MoE execution",
            ));
        }
        let max_fixture_elements = self.hello().limits().max_fixture_elements();
        let (_, value) = self.request_with_timeout(
            "run_synthetic_moe",
            request.protocol_params(),
            self.timeouts.request,
        )?;
        match parse_synthetic_moe_result(value, request, max_fixture_elements) {
            Ok(result) => Ok(result),
            Err(error) => {
                self.state = WorkerState::Failed;
                Err(error)
            }
        }
    }

    /// Request graceful shutdown and forcibly terminate only when the bounded
    /// graceful phase cannot complete.
    pub fn shutdown(mut self) -> CleanupReport {
        if self.state != WorkerState::Ready {
            let error = WorkerError::new(
                WorkerErrorKind::Protocol,
                "worker session is not ready for graceful shutdown",
            );
            return self.force_cleanup(error);
        }

        if let Err(error) =
            self.request_with_timeout("shutdown", Map::new(), self.timeouts.shutdown)
        {
            return self.force_cleanup(error);
        }
        self.state = WorkerState::ShuttingDown;
        self.stdin.take();

        let deadline = deadline_after(self.timeouts.shutdown);
        match self.wait_for_exit_until(deadline) {
            Ok(status) if status.success() => {
                self.state = WorkerState::Stopped;
                self.finish_reader();
                CleanupReport {
                    outcome: CleanupOutcome::Graceful,
                    exit_code: status.code(),
                    error: None,
                }
            }
            Ok(status) => {
                let error = error_from_exit_status(status);
                self.state = WorkerState::Stopped;
                self.finish_reader();
                CleanupReport {
                    outcome: CleanupOutcome::Failed,
                    exit_code: status.code(),
                    error: Some(error),
                }
            }
            Err(error) => self.force_cleanup(error),
        }
    }

    fn request_with_timeout(
        &mut self,
        operation: &str,
        params: Map<String, Value>,
        timeout: Duration,
    ) -> Result<(u64, Value), WorkerError> {
        if self.state != WorkerState::Ready {
            return Err(WorkerError::new(
                WorkerErrorKind::Protocol,
                "worker session does not admit requests in its current state",
            ));
        }

        let request_id = self.next_request_id;
        self.next_request_id = self.next_request_id.checked_add(1).ok_or_else(|| {
            WorkerError::new(
                WorkerErrorKind::Protocol,
                "worker request ID space is exhausted",
            )
        })?;
        let envelope = RequestEnvelope::new(request_id, operation, params)?;
        let encoded = envelope.encode_line(&self.limits)?;

        if let Err(error) = self.write_request(&encoded) {
            self.state = WorkerState::Failed;
            return Err(error);
        }
        let line = match self.receive_line(timeout) {
            Ok(line) => line,
            Err(error) => {
                self.state = WorkerState::Failed;
                return Err(error);
            }
        };
        let response = match parse_response_line(&line, request_id, &self.limits) {
            Ok(response) => response,
            Err(error) => {
                self.state = WorkerState::Failed;
                return Err(error);
            }
        };

        // A well-formed remote error is an operation result, not transport
        // corruption; callers may still perform controlled shutdown.
        let result = response.into_result()?;
        Ok((request_id, result))
    }

    fn write_request(&mut self, encoded: &[u8]) -> Result<(), WorkerError> {
        let Some(stdin) = self.stdin.as_mut() else {
            return Err(WorkerError::new(
                WorkerErrorKind::Io,
                "worker stdin is already closed",
            ));
        };
        if let Err(error) = stdin.write_all(encoded).and_then(|()| stdin.flush()) {
            if let Some(status) = self.try_wait()? {
                return Err(error_from_exit_status(status));
            }
            return Err(WorkerError::new(
                WorkerErrorKind::Io,
                format!("worker request could not be written: {error}"),
            ));
        }
        Ok(())
    }

    fn receive_line(&mut self, timeout: Duration) -> Result<Vec<u8>, WorkerError> {
        let deadline = deadline_after(timeout);
        let remaining = remaining_until(deadline).ok_or_else(timeout_error)?;
        match self.reader.recv_timeout(remaining) {
            Ok(ReaderEvent::Line(line)) => Ok(line),
            Ok(ReaderEvent::MessageTooLarge) => Err(WorkerError::new(
                WorkerErrorKind::MessageTooLarge,
                "worker stdout line exceeds the protocol-v1 byte limit",
            )),
            Ok(ReaderEvent::Io) => Err(WorkerError::new(
                WorkerErrorKind::Io,
                "worker stdout could not be read",
            )),
            Ok(ReaderEvent::Eof) | Err(RecvTimeoutError::Disconnected) => {
                self.classify_eof_until(deadline)
            }
            Err(RecvTimeoutError::Timeout) => match self.try_wait()? {
                Some(status) => Err(error_from_exit_status(status)),
                None => Err(timeout_error()),
            },
        }
    }

    fn classify_eof_until(&mut self, deadline: Instant) -> Result<Vec<u8>, WorkerError> {
        loop {
            if let Some(status) = self.try_wait()? {
                return Err(error_from_exit_status(status));
            }
            let Some(remaining) = remaining_until(deadline) else {
                return Err(WorkerError::new(
                    WorkerErrorKind::UnexpectedEof,
                    "worker stdout closed before a complete response",
                ));
            };
            thread::sleep(remaining.min(CHILD_STATUS_POLL_INTERVAL));
        }
    }

    fn try_wait(&mut self) -> Result<Option<ExitStatus>, WorkerError> {
        self.child.try_wait().map_err(|error| {
            WorkerError::new(
                WorkerErrorKind::Io,
                format!("worker exit status could not be read: {error}"),
            )
        })
    }

    fn wait_for_exit_until(&mut self, deadline: Instant) -> Result<ExitStatus, WorkerError> {
        loop {
            if let Some(status) = self.try_wait()? {
                return Ok(status);
            }
            let Some(remaining) = remaining_until(deadline) else {
                return Err(timeout_error());
            };
            thread::sleep(remaining.min(CHILD_STATUS_POLL_INTERVAL));
        }
    }

    fn force_cleanup(&mut self, error: WorkerError) -> CleanupReport {
        self.state = WorkerState::ShuttingDown;
        self.stdin.take();

        let mut status = self.child.try_wait().ok().flatten();
        let forced = status.is_none();
        if forced {
            let _ = self.child.kill();
            status = self.child.wait().ok();
        }
        self.state = WorkerState::Stopped;
        self.finish_reader();

        CleanupReport {
            outcome: if forced {
                CleanupOutcome::ForcedTermination
            } else {
                CleanupOutcome::Failed
            },
            exit_code: status.and_then(|status| status.code()),
            error: Some(error),
        }
    }

    fn finish_reader(&mut self) {
        let Some(handle) = self.reader_handle.take() else {
            return;
        };
        let deadline = deadline_after(READER_JOIN_BUDGET);
        while !handle.is_finished() {
            match self.reader.try_recv() {
                Ok(_) | Err(TryRecvError::Empty) => {}
                Err(TryRecvError::Disconnected) => break,
            }
            let Some(remaining) = remaining_until(deadline) else {
                // Detach rather than making a bounded shutdown wait forever if
                // an unrelated descendant inherited the stdout descriptor.
                return;
            };
            thread::sleep(remaining.min(CHILD_STATUS_POLL_INTERVAL));
        }
        let _ = handle.join();
    }
}

impl Drop for WorkerClient {
    fn drop(&mut self) {
        if self.state == WorkerState::Stopped {
            return;
        }
        self.stdin.take();
        if self.child.try_wait().ok().flatten().is_none() {
            let _ = self.child.kill();
        }
        let _ = self.child.wait();
        self.state = WorkerState::Stopped;
        self.finish_reader();
    }
}

fn spawn_stdout_reader(stdout: ChildStdout) -> (Receiver<ReaderEvent>, JoinHandle<()>) {
    let (sender, receiver) = mpsc::sync_channel(READER_CHANNEL_CAPACITY);
    let handle = thread::spawn(move || read_stdout(stdout, sender));
    (receiver, handle)
}

fn read_stdout(mut stdout: ChildStdout, sender: SyncSender<ReaderEvent>) {
    let mut frame = Vec::with_capacity(8 * 1024);
    let mut chunk = [0_u8; 8 * 1024];
    loop {
        match stdout.read(&mut chunk) {
            Ok(0) => {
                if frame.is_empty() {
                    let _ = sender.try_send(ReaderEvent::Eof);
                } else {
                    let _ = sender.send(ReaderEvent::Line(frame));
                }
                return;
            }
            Ok(count) => {
                for byte in &chunk[..count] {
                    frame.push(*byte);
                    if *byte == b'\n' {
                        if frame.len() - 1 > MAX_RESPONSE_BYTES {
                            let _ = sender.send(ReaderEvent::MessageTooLarge);
                            return;
                        }
                        if sender
                            .send(ReaderEvent::Line(std::mem::take(&mut frame)))
                            .is_err()
                        {
                            return;
                        }
                    } else if frame.len() > MAX_RESPONSE_BYTES {
                        let _ = sender.send(ReaderEvent::MessageTooLarge);
                        return;
                    }
                }
            }
            Err(_) => {
                let _ = sender.send(ReaderEvent::Io);
                return;
            }
        }
    }
}

fn deadline_after(timeout: Duration) -> Instant {
    Instant::now()
        .checked_add(timeout)
        .unwrap_or_else(Instant::now)
}

fn remaining_until(deadline: Instant) -> Option<Duration> {
    deadline.checked_duration_since(Instant::now())
}

fn timeout_error() -> WorkerError {
    WorkerError::new(
        WorkerErrorKind::Timeout,
        "worker operation exceeded its configured deadline",
    )
}

fn error_from_exit_status(status: ExitStatus) -> WorkerError {
    match status.code() {
        Some(0) => WorkerError::new(
            WorkerErrorKind::UnexpectedEof,
            "worker exited cleanly before completing the active operation",
        ),
        Some(code) => WorkerError::new(
            WorkerErrorKind::NonZeroExit,
            "worker exited with a nonzero status",
        )
        .with_exit_code(code),
        None => WorkerError::new(
            WorkerErrorKind::ProcessCrashed,
            "worker process terminated without an exit code",
        ),
    }
}

fn terminate_unowned_child(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}
