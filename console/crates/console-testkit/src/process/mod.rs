//! Provenance: translated from project-maya serve/test_stop.py (`free_port`, `fake_config`, `server_cmd`, `Proc`) at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! The helper that spawns a server process, waits for its ready line, sends signals and
//! reaps it.
//!
//! [`Proc`] is the donor's `Proc`: a child process whose output is read line by line on
//! background threads, so a test can wait for a line ([`Proc::until`]), read the server's
//! ready line ([`Proc::wait_ready`]), send it a signal ([`Proc::signal`], Unix only),
//! close its standard input ([`Proc::close_stdin`]), wait for its exit
//! ([`Proc::wait_exit`]), and read what it printed ([`Proc::rest`]). Dropping a `Proc`
//! kills and reaps the child, so a failing test leaves no process behind. The donor merges
//! standard error into standard output; here both streams are read, each on its own
//! thread, into one line queue, so each stream's lines keep their order but lines of the
//! two streams can interleave differently than a shared pipe would. The line queue holds
//! at most [`MAX_SEEN_LINES`] lines: a child that prints faster than the test reads waits
//! on its pipe instead of filling the test's memory (the donor's queue has no bound).
//!
//! [`spawn_locked`] starts a child under one process-wide lock, so that a child started by
//! one test thread cannot inherit a pipe end that another test thread is creating;
//! [`Proc::spawn`] and every direct spawn in a test binary that uses the kit go through it.
//!
//! [`fake_config`] writes the donor's `fake_config` set-up: a byte-level tokenizer folder
//! (GPT-2's byte map plus `<|im_end|>` and `</think>`) and a run config naming a fake
//! engine executable. [`ServerCommand`] builds the `pulsar-console` command line for it.
//!
//! # Seams
//!
//! The M1 binary `pulsar-console` exists since API-08, whose process tests start it through
//! [`Proc`]; it has no `--engine` option until API-17 (M4). The fake engine binaries are
//! ENG-05's (M3) and do not exist yet, so this module takes both paths as arguments and
//! its own tests drive `/bin/sh` scripts instead. The tests that spawn the server with the
//! fake engine (the donor's `ServerStops`) belong to API-17 and ENG-05, which use this
//! helper when they land. The process-group bookkeeping and leak checks of the conformance
//! harness (CNF-07, `console_conformance::process`) are not repeated here.
//!
//! Every program the kit starts is synthetic: a test script, the server under test on a
//! synthetic engine, or a fake engine. Nothing here is more than qualified on synthetic
//! backends.
//!
//! Behavior reference: project-maya serve/test_stop.py:40-112 at 7e68a30f.

use std::collections::VecDeque;
use std::io::{self, BufRead, BufReader, Read};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, ExitStatus, Stdio};
use std::sync::{mpsc, Mutex, MutexGuard};
use std::time::{Duration, Instant};

use serde_json::{Map, Value};

/// The most lines a [`Proc`] keeps in [`Proc::seen`]; older lines are dropped first.
pub const MAX_SEEN_LINES: usize = 100_000;

/// The most bytes of one output line a [`Proc`] keeps; the rest of the line is dropped.
pub const MAX_LINE_BYTES: usize = 64 * 1024;

/// The start of the server's ready line (contracts/cli.md, section 2).
pub const READY_PREFIX: &str = "ready: http://";

/// The run-config file name [`fake_config`] writes (the donor's `maya-fake.json`, with the
/// product prefix of B2).
pub const FAKE_CONFIG_NAME: &str = "pulsar-fake.json";

/// The tokenizer folder [`fake_config`] writes.
pub const FAKE_TOKENIZER_DIR: &str = "tokenizer";

/// The model name of the fake run config.
pub const FAKE_MODEL_NAME: &str = "fake";

/// The id of `<|im_end|>` in the fake tokenizer.
pub const FAKE_IM_END_ID: u32 = 256;

/// The id of `</think>` in the fake tokenizer.
pub const FAKE_THINK_END_ID: u32 = 257;

/// How long [`Proc::close`] waits for the child after killing it.
const REAP_WAIT: Duration = Duration::from_secs(30);

/// One line of output, or the end of one stream.
enum Line {
    Text(String),
    End,
}

/// The lock held across every child spawn of the kit; see [`spawn_locked`].
static SPAWN: Mutex<()> = Mutex::new(());

/// The spawn lock's guard. A test that panicked while holding it does not poison it for
/// the others.
fn spawn_guard() -> MutexGuard<'static, ()> {
    SPAWN
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

/// Starts `command` while holding the kit's process-wide spawn lock.
///
/// On macOS the standard library creates each pipe for a child's standard streams with
/// `pipe` and marks it close-on-exec with a second call, because the platform has no
/// `pipe2`. A child that another thread starts between those two calls inherits the
/// parent's end of that pipe and keeps it open. A reader of the first child's standard
/// input then sees no end of file after [`Proc::close_stdin`], and a reader of its output
/// sees no end of file after it exits, for as long as the other child or a descendant of
/// it lives. `Command::spawn` creates the pipes and starts the child, so one lock held
/// across every spawn of a test binary closes the window. [`Proc::spawn`] uses this
/// function; a test that also starts a child with `Command` directly starts it through
/// this function too, since a spawn that bypasses the lock reopens the window. On Linux
/// the pipes are created close-on-exec in one call and the lock only orders the spawns.
pub fn spawn_locked(command: &mut Command) -> io::Result<Child> {
    let _guard = spawn_guard();
    command.spawn()
}

/// A free loopback port: bound and released at once, as the donor's `free_port`. Another
/// process can take it before the caller does; the donor accepts the same race.
///
/// Behavior reference: project-maya serve/test_stop.py:40-43 at 7e68a30f.
pub fn free_port() -> io::Result<u16> {
    let listener = std::net::TcpListener::bind(("127.0.0.1", 0))?;
    Ok(listener.local_addr()?.port())
}

/// What a ready line names.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReadyAddr {
    /// The address as printed (without brackets for IPv6, as the donor prints it).
    pub host: String,
    /// The port.
    pub port: u16,
    /// The whole line.
    pub line: String,
}

/// Reads the address and port of a ready line
/// (`ready: http://<here>:<port>/v1  (...)`); `None` for any other line.
pub fn parse_ready(line: &str) -> Option<ReadyAddr> {
    let rest = line.strip_prefix(READY_PREFIX)?;
    let end = rest.find("/v1")?;
    let hostport = rest.get(..end)?;
    let (host, port) = hostport.rsplit_once(':')?;
    let port = port.parse().ok()?;
    if host.is_empty() {
        return None;
    }
    Some(ReadyAddr {
        host: host.to_owned(),
        port,
        line: line.to_owned(),
    })
}

/// A child process with its output read line by line.
#[derive(Debug)]
pub struct Proc {
    child: Child,
    stdin: Option<ChildStdin>,
    lines: mpsc::Receiver<Line>,
    streams_open: u8,
    seen: VecDeque<String>,
    status: Option<ExitStatus>,
}

/// Drops the rest of an over-long line, up to and including its `\n`, in steps of at most
/// one buffer, so a child that writes without a newline does not grow memory. Returns
/// false at the end of the stream or on a read error.
fn skip_line<R: BufRead>(reader: &mut R) -> bool {
    loop {
        let (consumed, found) = match reader.fill_buf() {
            Ok([]) | Err(_) => return false,
            Ok(buf) => match buf.iter().position(|&b| b == b'\n') {
                Some(i) => (i + 1, true),
                None => (buf.len(), false),
            },
        };
        reader.consume(consumed);
        if found {
            return true;
        }
    }
}

fn pump<R: Read + Send + 'static>(stream: R, tx: mpsc::SyncSender<Line>) {
    std::thread::spawn(move || {
        let mut reader = BufReader::new(stream);
        let mut buf = Vec::new();
        loop {
            buf.clear();
            match reader
                .by_ref()
                .take(MAX_LINE_BYTES as u64 + 1)
                .read_until(b'\n', &mut buf)
            {
                Ok(0) | Err(_) => break,
                Ok(_) => {
                    let full = buf.last() == Some(&b'\n');
                    buf.truncate(MAX_LINE_BYTES);
                    let text = String::from_utf8_lossy(&buf)
                        .trim_end_matches(['\n', '\r'])
                        .to_owned();
                    if tx.send(Line::Text(text)).is_err() {
                        return;
                    }
                    if !full && buf.len() >= MAX_LINE_BYTES && !skip_line(&mut reader) {
                        // An over-long line whose rest ran to the end of the stream.
                        break;
                    }
                }
            }
        }
        let _ = tx.send(Line::End);
    });
}

impl Proc {
    /// Starts `command` with standard output and standard error read by the helper and
    /// standard input a pipe (closed by [`close_stdin`](Self::close_stdin)).
    pub fn spawn(mut command: Command) -> io::Result<Self> {
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        let mut child = spawn_locked(&mut command)?;
        let (tx, rx) = mpsc::sync_channel(MAX_SEEN_LINES);
        let mut streams_open = 0;
        if let Some(out) = child.stdout.take() {
            pump(out, tx.clone());
            streams_open += 1;
        }
        if let Some(err) = child.stderr.take() {
            pump(err, tx);
            streams_open += 1;
        }
        let stdin = child.stdin.take();
        Ok(Self {
            child,
            stdin,
            lines: rx,
            streams_open,
            seen: VecDeque::new(),
            status: None,
        })
    }

    /// The child's process id.
    pub fn pid(&self) -> u32 {
        self.child.id()
    }

    /// The lines read so far (at most [`MAX_SEEN_LINES`], newest last).
    pub fn seen(&self) -> Vec<String> {
        self.seen.iter().cloned().collect()
    }

    fn keep(&mut self, line: String) {
        if self.seen.len() >= MAX_SEEN_LINES {
            self.seen.pop_front();
        }
        self.seen.push_back(line);
    }

    /// The next line within `timeout`; `None` when both streams ended or the time passed.
    fn next_line(&mut self, deadline: Instant) -> Option<String> {
        while self.streams_open > 0 {
            let left = deadline.saturating_duration_since(Instant::now());
            if left.is_zero() {
                return None;
            }
            match self.lines.recv_timeout(left) {
                Ok(Line::Text(t)) => {
                    self.keep(t.clone());
                    return Some(t);
                }
                Ok(Line::End) => self.streams_open = self.streams_open.saturating_sub(1),
                Err(mpsc::RecvTimeoutError::Timeout) => return None,
                Err(mpsc::RecvTimeoutError::Disconnected) => self.streams_open = 0,
            }
        }
        None
    }

    /// Waits up to `timeout` for a line containing `text`: true when one came, false when
    /// the output ended or the time passed first. Every line read is kept in
    /// [`seen`](Self::seen).
    ///
    /// Behavior reference: project-maya serve/test_stop.py:86-99 at 7e68a30f.
    pub fn until(&mut self, text: &str, timeout: Duration) -> bool {
        let deadline = Instant::now() + timeout;
        while let Some(line) = self.next_line(deadline) {
            if line.contains(text) {
                return true;
            }
        }
        false
    }

    /// Waits up to `timeout` for the server's ready line and returns what it names.
    pub fn wait_ready(&mut self, timeout: Duration) -> Option<ReadyAddr> {
        let deadline = Instant::now() + timeout;
        while let Some(line) = self.next_line(deadline) {
            if let Some(ready) = parse_ready(&line) {
                return Some(ready);
            }
        }
        None
    }

    /// The output once the process ended: reads what is left for up to `timeout`, then
    /// joins every line kept with `\n`.
    ///
    /// Behavior reference: project-maya serve/test_stop.py:111-114 at 7e68a30f.
    pub fn rest(&mut self, timeout: Duration) -> String {
        let deadline = Instant::now() + timeout;
        while self.next_line(deadline).is_some() {}
        self.seen().join("\n")
    }

    /// Sends signal `signal` (for example `libc::SIGTERM`) to the child.
    #[cfg(unix)]
    pub fn signal(&self, signal: i32) -> io::Result<()> {
        let pid = libc::pid_t::try_from(self.child.id())
            .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "pid out of range"))?;
        if self.status.is_some() {
            return Err(io::Error::new(
                io::ErrorKind::NotFound,
                "the process was already reaped",
            ));
        }
        // SAFETY: `kill` takes two integers and touches no memory of this process. The pid
        // is our own child's, which has not been reaped (checked above, and `Child` reaps
        // only through `wait`/`try_wait`, which record the status), so it cannot name a
        // reused pid of another process.
        let r = unsafe { libc::kill(pid, signal) };
        if r == 0 {
            Ok(())
        } else {
            Err(io::Error::last_os_error())
        }
    }

    /// Closes the child's standard input (the donor's parent-pipe end of file).
    pub fn close_stdin(&mut self) {
        self.stdin = None;
    }

    /// The child's standard input, while it is open.
    pub fn stdin(&mut self) -> Option<&mut ChildStdin> {
        self.stdin.as_mut()
    }

    /// The exit status, if the child has ended (without waiting).
    pub fn try_status(&mut self) -> io::Result<Option<ExitStatus>> {
        if self.status.is_none() {
            self.status = self.child.try_wait()?;
        }
        Ok(self.status)
    }

    /// Waits up to `timeout` for the child to end; `None` when it is still running.
    pub fn wait_exit(&mut self, timeout: Duration) -> io::Result<Option<ExitStatus>> {
        let deadline = Instant::now() + timeout;
        loop {
            if let Some(status) = self.try_status()? {
                return Ok(Some(status));
            }
            if Instant::now() >= deadline {
                return Ok(None);
            }
            std::thread::sleep(Duration::from_millis(10));
        }
    }

    /// Kills the child if it is still running and reaps it (the donor's `close`).
    pub fn close(&mut self) -> io::Result<ExitStatus> {
        if let Some(status) = self.try_status()? {
            return Ok(status);
        }
        let _ = self.child.kill();
        match self.wait_exit(REAP_WAIT)? {
            Some(status) => Ok(status),
            None => Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "the process did not end after kill",
            )),
        }
    }
}

impl Drop for Proc {
    fn drop(&mut self) {
        self.stdin = None;
        let _ = self.close();
    }
}

/// GPT-2's byte-level map, as the donor's `fake_config` builds it: the 256 byte values
/// each mapped to one printable character, and the vocabulary `{char: byte}` with
/// `<|im_end|>` at 256 and `</think>` at 257.
///
/// Behavior reference: project-maya serve/test_stop.py:49-52 at 7e68a30f.
pub fn byte_level_vocab() -> Map<String, Value> {
    let mut bs: Vec<u32> = (u32::from(b'!')..=u32::from(b'~'))
        .chain(0xa1..=0xac)
        .chain(0xae..=0xff)
        .collect();
    let mut cs = bs.clone();
    let mut extra = 0u32;
    for b in 0..256u32 {
        if !bs.contains(&b) {
            bs.push(b);
            cs.push(256 + extra);
            extra += 1;
        }
    }
    let mut vocab = Map::new();
    for (b, c) in bs.iter().zip(cs.iter()) {
        if let Some(ch) = char::from_u32(*c) {
            vocab.insert(ch.to_string(), Value::from(*b));
        }
    }
    vocab.insert("<|im_end|>".to_owned(), Value::from(FAKE_IM_END_ID));
    vocab.insert("</think>".to_owned(), Value::from(FAKE_THINK_END_ID));
    vocab
}

/// Writes the donor's fake set-up into `dir` and returns the run config's path: a
/// tokenizer folder with [`byte_level_vocab`] and a one-merge `merges.txt`, and a run
/// config `{"exe", "args": ["1"], "tokenizer", "model_name": "fake", "log"}` whose engine
/// is `engine_exe` (ENG-05's fake engine binary once it exists).
///
/// Behavior reference: project-maya serve/test_stop.py:46-65 at 7e68a30f.
pub fn fake_config(dir: &Path, engine_exe: &Path) -> io::Result<PathBuf> {
    let tok = dir.join(FAKE_TOKENIZER_DIR);
    std::fs::create_dir(&tok)?;
    let vocab = to_python(&Value::Object(byte_level_vocab()))?;
    std::fs::write(tok.join("vocab.json"), vocab)?;
    std::fs::write(tok.join("merges.txt"), "a b")?;
    let mut cfg = Map::new();
    cfg.insert("exe".to_owned(), Value::from(path_text(engine_exe)?));
    cfg.insert("args".to_owned(), Value::Array(vec![Value::from("1")]));
    cfg.insert("tokenizer".to_owned(), Value::from(path_text(&tok)?));
    cfg.insert("model_name".to_owned(), Value::from(FAKE_MODEL_NAME));
    cfg.insert(
        "log".to_owned(),
        Value::from(path_text(&dir.join("engine.log"))?),
    );
    let path = dir.join(FAKE_CONFIG_NAME);
    std::fs::write(&path, to_python(&Value::Object(cfg))?)?;
    Ok(path)
}

fn to_python(value: &Value) -> io::Result<String> {
    console_pyjson::dumps::to_python_default(value)
        .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, format!("{e:?}")))
}

fn path_text(path: &Path) -> io::Result<String> {
    path.to_str().map(str::to_owned).ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            "a path that is not UTF-8 cannot go into a run config",
        )
    })
}

/// The `pulsar-console` command line for a test: the binary, an engine choice, a run
/// config, a port, and any further arguments, in that order, as the donor's `server_cmd`
/// orders `--engine`, `--config` and `--port`. The flag names follow contracts/cli.md:
/// API-08 settled `--config` and `--port` (section 1.1), and `--engine` is API-17's, which
/// the M1 binary refuses as an unrecognized argument, so a command that names an engine is
/// a seam until then. The donor names its engine (`--engine maya` with a fake engine,
/// `--engine mock` without); a test names its own with [`engine`](Self::engine).
///
/// Behavior reference: project-maya serve/test_stop.py:68-70 at 7e68a30f (`server_cmd`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServerCommand {
    bin: PathBuf,
    engine: Option<String>,
    config: Option<PathBuf>,
    port: u16,
    extra: Vec<String>,
}

impl ServerCommand {
    /// `bin --port <port>`.
    pub fn new(bin: &Path, port: u16) -> Self {
        Self {
            bin: bin.to_path_buf(),
            engine: None,
            config: None,
            port,
            extra: Vec::new(),
        }
    }

    /// Adds `--engine <name>`, before `--config` as the donor's `server_cmd` puts it.
    pub fn engine(mut self, name: &str) -> Self {
        self.engine = Some(name.to_owned());
        self
    }

    /// Adds `--config <path>`.
    pub fn config(mut self, path: &Path) -> Self {
        self.config = Some(path.to_path_buf());
        self
    }

    /// Adds one more argument at the end.
    pub fn arg(mut self, arg: &str) -> Self {
        self.extra.push(arg.to_owned());
        self
    }

    /// The arguments after the binary.
    pub fn args(&self) -> Vec<String> {
        let mut args = Vec::new();
        if let Some(engine) = &self.engine {
            args.push("--engine".to_owned());
            args.push(engine.clone());
        }
        if let Some(config) = &self.config {
            args.push("--config".to_owned());
            args.push(config.to_string_lossy().into_owned());
        }
        args.push("--port".to_owned());
        args.push(self.port.to_string());
        args.extend(self.extra.iter().cloned());
        args
    }

    /// The command, ready for [`Proc::spawn`].
    pub fn command(&self) -> Command {
        let mut command = Command::new(&self.bin);
        command.args(self.args());
        command
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ready_lines_name_their_port() {
        let line = "ready: http://127.0.0.1:8090/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context 4096 tokens)";
        let r = parse_ready(line).expect("a ready line");
        assert_eq!((r.host.as_str(), r.port), ("127.0.0.1", 8090));
        assert_eq!(r.line, line);
        let v6 = parse_ready("ready: http://::1:9/v1  (x)").expect("an IPv6 ready line");
        assert_eq!((v6.host.as_str(), v6.port), ("::1", 9));
        for bad in [
            "ready http://127.0.0.1:1/v1",
            "ready: http://127.0.0.1/v1",
            "ready: http://:1/v1",
            "ready: http://h:99999/v1",
            "ready: http://h:1",
        ] {
            assert_eq!(parse_ready(bad), None, "{bad}");
        }
    }

    #[test]
    fn the_byte_level_vocabulary_is_gpt2s() {
        let v = byte_level_vocab();
        assert_eq!(v.len(), 258);
        assert_eq!(v.get("!"), Some(&Value::from(33)));
        // The space byte maps to U+0120, the first byte outside the printable runs to 256.
        assert_eq!(v.get("\u{120}"), Some(&Value::from(32)));
        assert_eq!(v.get("\u{100}"), Some(&Value::from(0)));
        assert_eq!(v.get("<|im_end|>"), Some(&Value::from(256)));
        assert_eq!(v.get("</think>"), Some(&Value::from(257)));
        let mut ids: Vec<u64> = v.values().filter_map(Value::as_u64).collect();
        ids.sort_unstable();
        ids.dedup();
        assert_eq!(ids.len(), 258, "every id once");
    }

    #[test]
    fn server_commands_put_the_port_last_before_extras() {
        let c = ServerCommand::new(Path::new("pulsar-console"), 8123)
            .config(Path::new("c.json"))
            .arg("--x");
        assert_eq!(
            c.args(),
            vec!["--config", "c.json", "--port", "8123", "--x"]
        );
        assert_eq!(
            ServerCommand::new(Path::new("b"), 1).args(),
            vec!["--port", "1"]
        );
        // The donor's order: `--engine maya --config <cfg> --port <port>`.
        assert_eq!(
            ServerCommand::new(Path::new("b"), 2)
                .config(Path::new("c.json"))
                .engine("fake")
                .args(),
            vec!["--engine", "fake", "--config", "c.json", "--port", "2"]
        );
    }

    #[test]
    fn an_over_long_line_is_skipped_in_bounded_steps() {
        let mut long = vec![b'x'; 3 * 8192];
        long.extend_from_slice(b"\nnext\n");
        let mut reader = BufReader::with_capacity(8192, &long[..]);
        assert!(skip_line(&mut reader));
        let mut rest = String::new();
        reader.read_line(&mut rest).expect("read");
        assert_eq!(rest, "next\n");
        let mut endless = BufReader::with_capacity(8192, &[b'y'; 20_000][..]);
        assert!(!skip_line(&mut endless), "the stream ended inside the line");
    }

    #[cfg(unix)]
    #[test]
    fn the_spawn_lock_survives_a_panicking_holder() {
        let result = std::thread::spawn(|| {
            let _guard = spawn_guard();
            panic!("a spawn panicked while holding the lock");
        })
        .join();
        assert!(result.is_err());
        drop(spawn_guard());
        let mut command = Command::new("/bin/sh");
        command.arg("-c").arg("exit 0").stdin(Stdio::null());
        let status = spawn_locked(&mut command).and_then(|mut child| child.wait());
        assert!(status.is_ok_and(|s| s.success()));
    }

    #[test]
    fn free_ports_are_not_zero() {
        assert_ne!(free_port().expect("a port"), 0);
    }
}
