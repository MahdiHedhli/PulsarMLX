//! Owned by API-08 in M1 (process-start synthetic-provenance refusal and the minimal entry
//! point for the checkpoint demonstration); API-17 extends it in M4.
//!
//! [`run`] is the entry function: it takes the command line and an engine factory maker,
//! and returns the process's exit status. The binary passes [`scripted_factory`], the
//! scripted engine of `console-engine::fake`; tests pass their own, which is how the
//! refusal of an engine that is not synthetic is shown at process start.
//!
//! # Start-up, in the donor's order
//!
//! 1. The command line ([`cli`]): a usage error exits 2 with the usage and the error on
//!    standard error.
//! 2. The run config of `--config` (API-15's document store) and the environment with its
//!    server entries laid over it (`PULSAR_CONSOLE_*`, contracts/naming.md).
//! 3. The host (`--host`, else the config's `host`, else `127.0.0.1`), then the port
//!    probe: before anything else is started, a port that cannot be bound is the donor's
//!    usage error `port N is already in use - ...` (exit 2).
//! 4. The server settings (API key, CORS origins, `allowed_hosts`, the turn-driver
//!    settings); an `allowed_hosts` entry that cannot be parsed stops the start with a
//!    message naming the entry and the accepted forms (lead decision LD40). The
//!    transport's settings (listen backlog, body limit, request timeout) are the resolved
//!    `http_backlog`, `max_body_mib` and `request_timeout_s` of these settings
//!    (`TransportConfig::from_settings`), so a run config's `env` entry for the backlog
//!    or the body limit wins over the environment, as the donor's `apply_server_env`
//!    makes it win; the timeout is not one of the donor's `SERVER_ENV` names, and only the
//!    environment sets it.
//! 5. The byte tokenizer, then the engine: the scripts of `--script`, or the donor's
//!    default script, encoded with the end-of-turn marker; the model name is the config's
//!    `model_name`, else `pulsar-console-synthetic` (deviation PLAN-2).
//! 6. The turn driver starts the engine through its admission step, which calls the
//!    synthetic-only guard `require_synthetic` (contracts/backend-seam.md section 5.1,
//!    rule 3; lead decision LD28). A refused engine makes the process print the guard's one
//!    line on standard error and exit 1, having served nothing.
//! 7. The router of API-03 with its guards, the inference driver of API-07 and the
//!    OpenAI Chat Completions dialect on `/v1/chat/completions`.
//! 8. When the run config lists CORS origins, the donor's line naming them
//!    (`[console] browser pages allowed to call /v1/* (CORS): ...`). The listener is
//!    bound; the line `[console] engine: ...` says that the engine is
//!    synthetic and that no real model is served (lead decision LD46); then the ready line
//!    of contracts/cli.md section 2 and the browser hint, on standard output, flushed.
//!    Under `--port 0` the ready line names the port the operating system bound (proposal
//!    P-25, awaiting the owner). The ready line carries no synthetic marker: that marker
//!    is only proposed (PLAN-1, FR-050, OPEN-35).
//!
//! Signals keep their default behavior in M1: the shutdown order, the second Ctrl+C, the
//! parent pipe and the log tee are API-17's and API-16's (M4).
//!
//! Nothing here reads a flag, an environment variable or a configuration key that could
//! select an engine: the maker the caller passes is the only engine the process can run,
//! and the binary passes only the scripted one. Nothing here is qualified beyond
//! synthetic backends.
//!
//! Behavior reference: project-maya serve/server.py:6744-6755, 7115-7175, 7285-7295,
//! 7320-7333 and 7376-7392 at 7e68a30f.

pub mod cli;

use std::ffi::OsString;
use std::future::Future;
use std::net::SocketAddr;
use std::sync::Arc;

use console_core::config::{
    load_document, names, CliOverrides, EnvSource, LayeredEnv, ProcessEnv, RunConfig,
    ServerSettings,
};
use console_core::engine::EngineFactory;
use console_core::fifo::{queue_ping_interval_from, EngineFifo, FifoLog};
use console_core::turn::{log_safe, NoObserver, TurnDriver, TurnSettings};
use console_engine::fake::{FakeScript, DEFAULT_MODEL_NAME, DEFAULT_SCRIPT_TEXT};
use console_http::dialect::openai::OpenAiDialect;
use console_http::guard::{invalid_allowed_hosts, GuardConfig};
use console_http::inference::{Inference, InferenceSettings};
use console_http::router::{Route, Router};
use console_http::transport::{bind_host, probe_port, Listener, TransportConfig};
use console_pyjson::loads::truthy;
use console_tokenizer::byte_tok::ByteTokenizer;
use serde_json::Value;

pub use cli::{Options, Parsed, UsageError};

/// The end-of-turn literal the scripted engine's answers end with.
///
/// Behavior reference: project-maya serve/server.py:160 and 209-211 at 7e68a30f.
pub const IM_END: &str = "<|im_end|>";

/// The accepted forms of an `allowed_hosts` entry, named when one cannot be parsed.
pub const ALLOWED_HOSTS_FORMS: &str = "name, name:port, [v6] or [v6]:port";

/// The line printed before the ready line: the engine is synthetic, and no real model is
/// served (lead decision LD46).
pub const SYNTHETIC_ENGINE_LINE: &str =
    "[console] engine: scripted, synthetic provenance - no real model is served";

/// What an engine factory maker receives: the scripts, already encoded, and the
/// environment with the run config's server entries laid over it.
pub struct EngineSpec<'a> {
    /// The scripted answers: each request takes the next, and the last one repeats.
    pub scripts: Vec<Vec<u32>>,
    /// The environment the engine reads its settings from
    /// (`PULSAR_CONSOLE_MOCK_TOK_S`, `PULSAR_CONSOLE_MOCK_RELOAD_S`).
    pub env: &'a dyn EnvSource,
}

impl std::fmt::Debug for EngineSpec<'_> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("EngineSpec")
            .field("scripts", &self.scripts.len())
            .finish_non_exhaustive()
    }
}

/// The binary's engine: the scripted engine of `console-engine::fake` (the donor's
/// `MockEngine`) with the spec's scripts, its default context and the speed and reload
/// delay the environment gives. It reports synthetic provenance.
///
/// Behavior reference: project-maya serve/server.py:7285-7289 at 7e68a30f.
pub fn scripted_factory(spec: &EngineSpec<'_>) -> Result<Arc<dyn EngineFactory>, String> {
    let factory = FakeScript::rotating(spec.scripts.clone())
        .apply_env(|name| spec.env.var(name))
        .and_then(FakeScript::build)
        .map_err(|e| e.to_string())?;
    Ok(Arc::new(factory))
}

/// Where the process's lines go: standard output and standard error, or captures in
/// tests.
#[derive(Debug, Clone)]
pub struct Console {
    /// Standard output: the ready line and the server's own log lines.
    pub out: FifoLog,
    /// Standard error: usage errors, start-up failures and the error log.
    pub err: FifoLog,
}

impl Console {
    /// The process's own streams, each line flushed as it is written.
    pub fn process() -> Self {
        Self {
            out: FifoLog::stdout(),
            err: FifoLog::new(|line| {
                use std::io::Write;
                let mut err = std::io::stderr().lock();
                let _ = writeln!(err, "{line}");
                let _ = err.flush();
            }),
        }
    }
}

/// A start that did not reach the ready line: the exit status, its lines already printed.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Exit(pub i32);

/// A started server: bound, its ready line printed, not yet accepting connections.
pub struct Started {
    listener: Listener,
    router: Arc<Router>,
    driver: TurnDriver,
    addr: SocketAddr,
}

impl std::fmt::Debug for Started {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Started")
            .field("addr", &self.addr)
            .finish_non_exhaustive()
    }
}

impl Started {
    /// The bound address.
    pub fn addr(&self) -> SocketAddr {
        self.addr
    }

    /// The settings the bound listener uses: its listen backlog, body limit and request
    /// timeout. Read-only.
    pub fn transport(&self) -> TransportConfig {
        self.listener.config()
    }

    /// The turn driver.
    pub fn driver(&self) -> &TurnDriver {
        &self.driver
    }

    /// Serves until `shutdown` resolves, then lets the requests in flight finish and
    /// closes the engine.
    pub async fn serve<S: Future<Output = ()>>(self, shutdown: S) {
        let mut in_flight = self.listener.serve(self.router, shutdown).await;
        while in_flight.join_next().await.is_some() {}
        self.driver.close().await;
    }
}

/// The ready line of contracts/cli.md section 2: the address clients use (`127.0.0.1`
/// for an address that means every interface), the port, the context, and whether
/// pictures are on and an API key is required.
///
/// Behavior reference: project-maya serve/server.py:7385-7390 at 7e68a30f.
pub fn ready_lines(host: &str, port: u16, context: u32, images: bool, keyed: bool) -> [String; 2] {
    let here = if matches!(host, "0.0.0.0" | "" | "::") {
        "127.0.0.1"
    } else {
        host
    };
    let ready = format!(
        "ready: http://{here}:{port}/v1  (OpenAI: /v1/chat/completions, /v1/responses, \
         Anthropic: /v1/messages, context {context} tokens{}{})",
        if images { ", images on" } else { "" },
        if keyed { ", API key required" } else { "" }
    );
    let hint = format!(
        "       open http://{here}:{port}/ in a browser to chat; close this window to stop the \
         model"
    );
    [ready, hint]
}

/// The start-up line for the run config's CORS origins, with the product's prefix
/// (BRAND-1), the origins made log-safe (lead decision LD35).
///
/// Behavior reference: project-maya serve/server.py:7330-7331 at 7e68a30f.
pub fn cors_line(origins: &[String]) -> String {
    format!(
        "[console] browser pages allowed to call /v1/* (CORS): {}",
        log_safe(&origins.join(", "))
    )
}

/// The donor's message when the port probe fails, with the product's name (BRAND-1).
///
/// Behavior reference: project-maya serve/server.py:7166-7171 at 7e68a30f.
pub fn port_in_use_message(port: i64) -> String {
    format!(
        "port {port} is already in use - is PulsarMLX Console (or another server) already \
         running? Close it, or start this one with a different --port"
    )
}

/// Prints a refused `sampling` block of the run config as the donor's start-up does: its
/// "unknown key, ignored" notes on standard output, then its message on standard error.
/// The caller exits non-zero. (The scripted engine's start reads no `sampling` block, as
/// the donor's mock path does not; the line engine's start of API-17 calls this.)
///
/// Behavior reference: project-maya serve/server.py:6957 and 7208-7215 at 7e68a30f.
pub fn report_sampling_error(console: &Console, e: &console_core::sampling::ConfigSamplingError) {
    for note in e.notes() {
        console.out.line(note);
    }
    console.err.line(e.message());
}

fn usage_error(console: &Console, columns: usize, message: String) -> Exit {
    for line in cli::usage_error_text(&UsageError(message), columns).lines() {
        console.err.line(line);
    }
    Exit(2)
}

fn config_error(console: &Console, e: &dyn std::fmt::Display) -> Exit {
    console
        .err
        .line(&format!("config: {}", log_safe(&e.to_string())));
    Exit(1)
}

/// Starts the server with these options: every step up to and including the ready line.
/// `make_engine` builds the only engine the process can run; `env` is the process's
/// environment (an injected map in tests). On failure the lines are printed and the exit
/// status is returned.
pub async fn start<F>(
    opts: &Options,
    make_engine: F,
    console: &Console,
    env: &dyn EnvSource,
) -> Result<Started, Exit>
where
    F: FnOnce(&EngineSpec<'_>) -> Result<Arc<dyn EngineFactory>, String>,
{
    let columns = cli::columns_from(env.var("COLUMNS").as_deref());
    let cfg = match &opts.config {
        Some(path) => {
            load_document(std::path::Path::new(path)).map_err(|e| config_error(console, &e))?
        }
        None => RunConfig::new(),
    };
    let layered = LayeredEnv::new(env, &cfg).map_err(|e| config_error(console, &e))?;
    let host = cfg
        .host(opts.host.as_deref())
        .map_err(|e| config_error(console, &e))?;
    // Before anything is started: is the port free? A port no socket takes is the
    // OverflowError CPython's bind raises, which the donor does not catch.
    let port = match opts.port.and_then(|p| u16::try_from(p).ok()) {
        Some(p) => p,
        None => {
            console
                .err
                .line("OverflowError: bind(): port must be 0-65535.");
            return Err(Exit(1));
        }
    };
    if probe_port(&host, port).is_err() {
        return Err(usage_error(
            console,
            columns,
            port_in_use_message(i64::from(port)),
        ));
    }
    let cli_overrides = CliOverrides {
        host: opts.host.clone(),
        api_key: Option::clone(&opts.api_key),
        fit_max_tokens: false,
        idle_unload_s: None,
    };
    let settings = ServerSettings::resolve(&cli_overrides, &env, &cfg)
        .map_err(|e| config_error(console, &e))?;
    // Lead decision LD40: an entry that can never match stops the start.
    if let Some(hosts) = &settings.allowed_hosts {
        let rejected = invalid_allowed_hosts(hosts);
        if let Some(first) = rejected.first() {
            console.err.line(&format!(
                "config: allowed_hosts: {} is not a host name the server can match; the \
                 accepted forms are {ALLOWED_HOSTS_FORMS}",
                log_safe(&console_core::request::pyrepr::repr_str(first))
            ));
            return Err(Exit(1));
        }
    }
    // The transport's settings are the resolved ones (the run config's `env` block laid
    // over the environment): the same values `EnvSettings` reports, so no second reading
    // of the variables can drift from them.
    let transport = TransportConfig::from_settings(&settings.env);
    let tok = Arc::new(ByteTokenizer::new());
    let end = tok.encode(IM_END, true, &[]);
    let texts: Vec<&str> = if opts.scripts.is_empty() {
        vec![DEFAULT_SCRIPT_TEXT]
    } else {
        opts.scripts.iter().map(String::as_str).collect()
    };
    let scripts = texts
        .iter()
        .map(|t| {
            let mut ids = tok.encode(t, true, &[]);
            ids.extend_from_slice(&end);
            ids
        })
        .collect();
    let spec = EngineSpec {
        scripts,
        env: &layered,
    };
    let factory = match make_engine(&spec) {
        Ok(f) => f,
        Err(message) => {
            console
                .err
                .line(&format!("[console] {}", log_safe(&message)));
            return Err(Exit(1));
        }
    };
    let model = cfg
        .get("model_name")
        .cloned()
        .unwrap_or_else(|| Value::String(DEFAULT_MODEL_NAME.to_owned()));
    let turn_settings = TurnSettings {
        fit_max_tokens: settings.fit_max_tokens,
        queue_ping: queue_ping_interval_from(layered.var(names::QUEUE_PING_S).as_deref()),
        ..TurnSettings::default()
    };
    let fifo = EngineFifo::with_log(1, console.out.clone());
    // The admission step of the turn driver calls `require_synthetic` before the engine
    // serves anything (contracts/backend-seam.md section 5.1, rule 3).
    let driver = match TurnDriver::start(
        factory,
        fifo,
        turn_settings,
        Arc::new(NoObserver),
        console.out.clone(),
    )
    .await
    {
        Ok(d) => d,
        Err(failure) => {
            let message = log_safe(failure.message.as_str());
            if message.starts_with("[console] ") {
                console.err.line(&message);
            } else {
                console
                    .err
                    .line(&format!("[console] the engine did not start: {message}"));
            }
            return Err(Exit(1));
        }
    };
    // The donor's CORS line, printed once the engine is up and before the server binds.
    if !settings.cors_origins.is_empty() {
        console.out.line(&cors_line(&settings.cors_origins));
    }
    let listener = match bind_host(&host, port, transport) {
        Ok(l) => l,
        Err(e) => {
            driver.close().await;
            console.err.line(&format!(
                "[console] could not listen on {}:{port}: {e}",
                log_safe(&host)
            ));
            return Err(Exit(1));
        }
    };
    let addr = match listener.local_addr() {
        Ok(a) => a,
        Err(e) => {
            driver.close().await;
            console
                .err
                .line(&format!("[console] could not read the bound address: {e}"));
            return Err(Exit(1));
        }
    };
    let guard = GuardConfig::new(addr.ip())
        .with_api_key(&settings.api_key)
        .with_cors_origins(settings.cors_origins.clone())
        .with_allowed_hosts(settings.allowed_hosts.clone());
    let mut router = Router::new(guard);
    let inference = Arc::new(
        Inference::new(driver.clone())
            .with_settings(InferenceSettings::from_env(&settings.env))
            .with_log(console.out.clone())
            .with_error_log(console.err.clone()),
    );
    let vocab = u32::try_from(tok.n_vocab()).ok();
    let dialect = OpenAiDialect::synthetic(tok, model, vocab);
    inference.register(&mut router, Route::ChatCompletions, Arc::new(dialect));
    console.out.line(SYNTHETIC_ENGINE_LINE);
    let keyed = truthy(&settings.api_key);
    for line in ready_lines(&host, addr.port(), driver.max_context(), false, keyed) {
        console.out.line(&line);
    }
    Ok(Started {
        listener,
        router: Arc::new(router),
        driver,
        addr,
    })
}

/// A panic hook that writes one line, `[console] panic at <file:line>: <message>`, on
/// standard error, so that a caught panic (the transport and the turn driver catch the
/// ones they can) keeps the logs to one line each.
fn install_panic_hook() {
    std::panic::set_hook(Box::new(|info| {
        let message = info
            .payload()
            .downcast_ref::<&str>()
            .map(|s| (*s).to_owned())
            .or_else(|| info.payload().downcast_ref::<String>().cloned())
            .unwrap_or_else(|| "a panic".to_owned());
        let place = info
            .location()
            .map(|l| format!("{}:{}", l.file(), l.line()))
            .unwrap_or_default();
        // Not `eprintln!`: it panics when standard error cannot be written (a closed
        // pipe), and a panic inside the hook aborts the process.
        use std::io::Write;
        let mut err = std::io::stderr().lock();
        let _ = writeln!(err, "[console] panic at {place}: {}", log_safe(&message));
        let _ = err.flush();
    }));
}

/// The entry function: reads `args` (the program name first), starts the server with the
/// engine `make_engine` builds, and serves until the process is stopped. Returns the exit
/// status: 0 after `--help`, 2 for a usage error, 1 for a start-up failure (the
/// synthetic-only refusal among them).
pub fn run<I, F>(args: I, make_engine: F) -> i32
where
    I: IntoIterator<Item = OsString>,
    F: FnOnce(&EngineSpec<'_>) -> Result<Arc<dyn EngineFactory>, String>,
{
    let console = Console::process();
    let env = ProcessEnv;
    let columns = cli::columns_from(env.var("COLUMNS").as_deref());
    let args: Vec<String> = args
        .into_iter()
        .skip(1)
        .map(|a| a.to_string_lossy().into_owned())
        .collect();
    let opts = match cli::parse(&args) {
        Ok(Parsed::Run(opts)) => opts,
        Ok(Parsed::Help) => {
            console.out.line(&cli::help(columns));
            return 0;
        }
        Err(UsageError(message)) => return usage_error(&console, columns, message).0,
    };
    install_panic_hook();
    let runtime = match tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
    {
        Ok(rt) => rt,
        Err(e) => {
            console
                .err
                .line(&format!("[console] the async runtime did not start: {e}"));
            return 1;
        }
    };
    runtime.block_on(async {
        match start(&opts, make_engine, &console, &env).await {
            Ok(started) => {
                started.serve(std::future::pending::<()>()).await;
                0
            }
            Err(Exit(code)) => code,
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_ready_line_has_the_donor_form() {
        let [ready, hint] = ready_lines("127.0.0.1", 8095, 32768, false, false);
        assert_eq!(
            ready,
            "ready: http://127.0.0.1:8095/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context 32768 tokens)"
        );
        assert_eq!(
            hint,
            "       open http://127.0.0.1:8095/ in a browser to chat; close this window to stop the model"
        );
        for any in ["0.0.0.0", "", "::"] {
            assert!(ready_lines(any, 1, 2, false, false)[0]
                .starts_with("ready: http://127.0.0.1:1/v1  ("));
        }
        // An IPv6 address is printed bare, as the donor prints it.
        assert!(ready_lines("::1", 9, 2, false, false)[0].starts_with("ready: http://::1:9/v1  ("));
        assert!(ready_lines("h", 1, 2, true, true)[0]
            .ends_with("context 2 tokens, images on, API key required)"));
        assert_eq!(
            port_in_use_message(8095),
            "port 8095 is already in use - is PulsarMLX Console (or another server) already running? Close it, or start this one with a different --port"
        );
    }
}
