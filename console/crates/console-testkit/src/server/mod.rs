//! `TestServer::builder()`: an in-process server on a loopback port the system chooses,
//! over the API-02 transport, with the API-03 router and guards, and optionally the turn
//! driver of ENG-10 around a chosen synthetic engine.
//!
//! The donor's HTTP tests build a `Service` around a test engine, a byte tokenizer and a
//! chat template, then `serve(svc, port=0)`. The builder is the same set-up in Rust:
//!
//! - the transport is bound on `127.0.0.1:0` (or another address of the caller's choice)
//!   with [`TransportConfig`] read from the injected environment and the run config's
//!   `env` block, as the server reads them, never from the process's own environment (so a
//!   test is not changed by the shell it runs in);
//! - requests go to a [`Router`] built from the guard settings (API key, CORS origins,
//!   `allowed_hosts`, given one by one or read from a [`RunConfig`]), with the handlers the
//!   test registers; or, for transport tests, to one raw [`Handler`];
//! - with [`TestServerBuilder::engine`], a [`TurnDriver`] starts the engine through the
//!   synthetic-only admission step and is handed, with the byte tokenizer, the injected
//!   environment, clock and configuration folder, to handler factories
//!   ([`TestServerBuilder::route_with`]), so later packages register their real handlers
//!   on the same server.
//!
//! The chat template fixture of the planner's detail is a seam: templates arrive with
//! PRM-03 in M2, and PRM-02 extends this kit with them.
//!
//! Nothing here admits an engine the server would refuse: the driver runs
//! `require_synthetic` on every engine it starts, so a test that hands it a non-synthetic
//! double gets the refusal as [`StartError::Engine`].
//!
//! Behavior reference: project-maya serve/test_server.py:1673-1681, 2042-2048 and
//! 2364-2370 at 7e68a30f (the donor's set-up), serve/server.py:7376-7390 at 7e68a30f
//! (`serve`).

pub mod probe;
mod temp;

use std::collections::BTreeMap;
use std::fmt;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::{Path, PathBuf};
use std::sync::Arc;

use console_core::config::{names, ConfigError, EnvSettings, RunConfig};
use console_core::engine::{EngineFactory, EngineFailure};
use console_core::fifo::{queue_ping_interval_from, EngineFifo, FifoLog, LogCapture};
use console_core::turn::{NoObserver, TurnDriver, TurnObserver, TurnSettings};
use console_engine::fake::FakeClock;
use console_http::guard::GuardConfig;
use console_http::router::{Route, RouteHandler, Router};
use console_http::transport::{bind, Handler, TransportConfig};
use console_tokenizer::byte_tok::ByteTokenizer;
use serde_json::Value;
use tokio::sync::oneshot;
use tokio::task::{JoinHandle, JoinSet};

use crate::raw::{self, RawRequest, RawResponse};
use crate::sse::SseReader;

pub use temp::TempDir;

/// The loopback address the kit binds by default.
pub const LOOPBACK: IpAddr = IpAddr::V4(Ipv4Addr::LOCALHOST);

/// What a handler factory receives: the parts of the server it may build on.
#[derive(Clone)]
pub struct Parts {
    /// The turn driver, when the server was given an engine.
    pub driver: Option<TurnDriver>,
    /// The byte tokenizer (the donor's `ByteTokenizer`).
    pub tokenizer: Arc<ByteTokenizer>,
    /// The injected environment: names to values, as the server would read them.
    pub env: Arc<BTreeMap<String, String>>,
    /// The injected clock, when the test gave one.
    pub clock: Option<Arc<dyn FakeClock>>,
    /// The configuration folder, when the test asked for one.
    pub config_dir: Option<PathBuf>,
    /// The run config the guards were read from (empty when none was given).
    pub run_config: RunConfig,
    /// The transport settings in force.
    pub transport: TransportConfig,
}

impl fmt::Debug for Parts {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Parts")
            .field("driver", &self.driver.is_some())
            .field("env", &self.env)
            .field("clock", &self.clock.is_some())
            .field("config_dir", &self.config_dir)
            .field("transport", &self.transport)
            .finish_non_exhaustive()
    }
}

impl Parts {
    /// The injected value of the environment variable `name`.
    pub fn env_var(&self, name: &str) -> Option<&str> {
        self.env.get(name).map(String::as_str)
    }
}

/// A handler factory, called once at start with the server's [`Parts`].
pub type RouteFactory = Box<dyn FnOnce(&Parts) -> Arc<dyn RouteHandler> + Send>;

enum RouteSource {
    Handler(Arc<dyn RouteHandler>),
    Factory(RouteFactory),
}

enum ConfigDir {
    None,
    Path(PathBuf),
    Temp,
}

/// Why a test server did not start.
#[derive(Debug)]
pub enum StartError {
    /// The listener could not be bound.
    Bind(std::io::Error),
    /// The run config held a guard setting the server refuses at start.
    Config(ConfigError),
    /// The engine did not start, or was refused by the synthetic-only guard.
    Engine(EngineFailure),
    /// The temporary configuration folder could not be made.
    TempDir(std::io::Error),
    /// The builder was given settings that would be ignored: a raw handler with router
    /// settings or routes, or a whole router or guard configuration with separate guard
    /// settings.
    Conflict(&'static str),
}

impl fmt::Display for StartError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Bind(e) => write!(f, "bind: {e}"),
            Self::Config(e) => write!(f, "config: {e}"),
            Self::Engine(e) => write!(f, "engine: {e}"),
            Self::TempDir(e) => write!(f, "temporary folder: {e}"),
            Self::Conflict(what) => write!(f, "conflicting builder settings: {what}"),
        }
    }
}

impl std::error::Error for StartError {}

/// The settings of a [`TestServer`]. Start with [`TestServer::builder`].
pub struct TestServerBuilder {
    bind: IpAddr,
    transport: Option<TransportConfig>,
    env: BTreeMap<String, String>,
    guard: Option<GuardConfig>,
    api_key: Option<Value>,
    cors_origins: Option<Vec<String>>,
    allowed_hosts: Option<Option<Vec<String>>>,
    run_config: Option<RunConfig>,
    handler: Option<Arc<dyn Handler>>,
    router: Option<Router>,
    routes: Vec<(Route, RouteSource)>,
    engine: Option<Arc<dyn EngineFactory>>,
    turn_settings: Option<TurnSettings>,
    observer: Option<Arc<dyn TurnObserver>>,
    capacity: usize,
    clock: Option<Arc<dyn FakeClock>>,
    config_dir: ConfigDir,
}

impl fmt::Debug for TestServerBuilder {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("TestServerBuilder")
            .field("bind", &self.bind)
            .field("transport", &self.transport)
            .field("env", &self.env)
            .field("engine", &self.engine.is_some())
            .field("routes", &self.routes.len())
            .finish_non_exhaustive()
    }
}

impl Default for TestServerBuilder {
    fn default() -> Self {
        Self {
            bind: LOOPBACK,
            transport: None,
            env: BTreeMap::new(),
            guard: None,
            api_key: None,
            cors_origins: None,
            allowed_hosts: None,
            run_config: None,
            handler: None,
            router: None,
            routes: Vec::new(),
            engine: None,
            turn_settings: None,
            observer: None,
            capacity: 1,
            clock: None,
            config_dir: ConfigDir::None,
        }
    }
}

impl TestServerBuilder {
    /// Binds another address than `127.0.0.1` (port 0 always). The guards follow the bind
    /// address, as the server's do (SEC-1.1).
    pub fn bind(mut self, ip: IpAddr) -> Self {
        self.bind = ip;
        self
    }

    /// The transport settings; by default they are read as the server reads them, from
    /// the injected environment (`PULSAR_CONSOLE_HTTP_BACKLOG`,
    /// `PULSAR_CONSOLE_MAX_BODY_MIB`, `PULSAR_CONSOLE_REQUEST_TIMEOUT_S`, empty unless the
    /// test sets it) with the server entries of the `env` block of the
    /// [`run_config`](Self::run_config) laid over it (the backlog and the body limit; the
    /// donor's `SERVER_ENV` does not name the timeout).
    pub fn transport(mut self, config: TransportConfig) -> Self {
        self.transport = Some(config);
        self
    }

    /// Sets one variable of the injected environment. The process environment is never
    /// read or changed.
    pub fn env(mut self, name: &str, value: &str) -> Self {
        self.env.insert(name.to_owned(), value.to_owned());
        self
    }

    /// The whole guard configuration, instead of the settings below (giving both fails the
    /// start with [`StartError::Conflict`]).
    pub fn guard(mut self, config: GuardConfig) -> Self {
        self.guard = Some(config);
        self
    }

    /// The API key setting (a string, or a list of keys), as the run config's `api_key`.
    pub fn api_key(mut self, setting: Value) -> Self {
        self.api_key = Some(setting);
        self
    }

    /// The browser origins allowed to call `/v1/*`.
    pub fn cors_origins(mut self, origins: Vec<String>) -> Self {
        self.cors_origins = Some(origins);
        self
    }

    /// The `allowed_hosts` list (SEC-1.1); `None` is the default (loopback names only on a
    /// loopback bind).
    pub fn allowed_hosts(mut self, hosts: Option<Vec<String>>) -> Self {
        self.allowed_hosts = Some(hosts);
        self
    }

    /// A run config to read the guard settings from (`api_key`, `cors_origins`,
    /// `allowed_hosts`), with the injected `PULSAR_CONSOLE_API_KEY` taking precedence over
    /// its `api_key`, as at server start. Settings given one by one win over it. Its `env`
    /// block's server entries win over the injected environment for the transport
    /// settings, as at server start.
    pub fn run_config(mut self, config: RunConfig) -> Self {
        self.run_config = Some(config);
        self
    }

    /// Serves every request with this raw transport handler instead of a router.
    pub fn handler(mut self, handler: Arc<dyn Handler>) -> Self {
        self.handler = Some(handler);
        self
    }

    /// Serves requests with this router as it is (its guards included); routes registered
    /// with [`route`](Self::route) are added to it. The router keeps its own guards, so
    /// giving guard settings as well ([`guard`](Self::guard), [`api_key`](Self::api_key),
    /// [`cors_origins`](Self::cors_origins), [`allowed_hosts`](Self::allowed_hosts),
    /// [`run_config`](Self::run_config)) fails the start with [`StartError::Conflict`].
    pub fn router(mut self, router: Router) -> Self {
        self.router = Some(router);
        self
    }

    /// Registers `handler` for `route`.
    pub fn route(mut self, route: Route, handler: Arc<dyn RouteHandler>) -> Self {
        self.routes.push((route, RouteSource::Handler(handler)));
        self
    }

    /// Registers the handler `factory` builds, at start, from the server's [`Parts`] (the
    /// turn driver among them).
    pub fn route_with(
        mut self,
        route: Route,
        factory: impl FnOnce(&Parts) -> Arc<dyn RouteHandler> + Send + 'static,
    ) -> Self {
        self.routes
            .push((route, RouteSource::Factory(Box::new(factory))));
        self
    }

    /// Starts this engine behind a turn driver. It must be synthetic: the driver's
    /// admission step refuses anything else, and the start fails.
    pub fn engine(mut self, factory: Arc<dyn EngineFactory>) -> Self {
        self.engine = Some(factory);
        self
    }

    /// The turn driver's settings; by default [`TurnSettings::default`] with the queue
    /// keep-alive interval read from the injected `PULSAR_CONSOLE_QUEUE_PING_S`.
    pub fn turn_settings(mut self, settings: TurnSettings) -> Self {
        self.turn_settings = Some(settings);
        self
    }

    /// An observer of the turns (history, figures).
    pub fn observer(mut self, observer: Arc<dyn TurnObserver>) -> Self {
        self.observer = Some(observer);
        self
    }

    /// The places of the engine FIFO before the engine reports its own (1 by default).
    pub fn places(mut self, n: usize) -> Self {
        self.capacity = n.max(1);
        self
    }

    /// A clock handed to handler factories (the engine's own clock is set on its script).
    pub fn clock(mut self, clock: Arc<dyn FakeClock>) -> Self {
        self.clock = Some(clock);
        self
    }

    /// Uses `dir` as the configuration folder (it is not removed afterwards).
    pub fn config_dir(mut self, dir: &Path) -> Self {
        self.config_dir = ConfigDir::Path(dir.to_path_buf());
        self
    }

    /// Makes a fresh temporary configuration folder, removed when the server is dropped.
    pub fn temp_config_dir(mut self) -> Self {
        self.config_dir = ConfigDir::Temp;
        self
    }

    fn guard_config(&self) -> Result<(GuardConfig, RunConfig), StartError> {
        let run_config = self.run_config.clone().unwrap_or_default();
        if let Some(guard) = &self.guard {
            return Ok((guard.clone(), run_config));
        }
        let env_key = self.env.get(names::API_KEY).map_or("", String::as_str);
        let api_key = match &self.api_key {
            Some(setting) => setting.clone(),
            None => run_config.api_key(None, env_key),
        };
        let cors = match &self.cors_origins {
            Some(origins) => origins.clone(),
            None => run_config.cors_origins().map_err(StartError::Config)?,
        };
        let hosts = match &self.allowed_hosts {
            Some(hosts) => hosts.clone(),
            None => run_config.allowed_hosts().map_err(StartError::Config)?,
        };
        let config = GuardConfig::new(self.bind)
            .with_api_key(&api_key)
            .with_cors_origins(cors)
            .with_allowed_hosts(hosts);
        Ok((config, run_config))
    }

    /// The transport settings given, or the resolved ones as the server builds them: the
    /// run config's `env` block laid over the injected environment
    /// (`EnvSettings::resolve`), then `TransportConfig::from_settings`.
    fn transport_config(&self) -> Result<TransportConfig, StartError> {
        if let Some(config) = self.transport {
            return Ok(config);
        }
        let empty = RunConfig::new();
        let run_config = self.run_config.as_ref().unwrap_or(&empty);
        let settings = EnvSettings::resolve(&self.env, run_config).map_err(StartError::Config)?;
        Ok(TransportConfig::from_settings(&settings))
    }

    /// Starts the server: the engine (if any) through the synthetic-only admission step,
    /// then the listener on port 0.
    pub async fn start(self) -> Result<TestServer, StartError> {
        let routed = self.router.is_some()
            || !self.routes.is_empty()
            || self.guard.is_some()
            || self.api_key.is_some()
            || self.cors_origins.is_some()
            || self.allowed_hosts.is_some()
            || self.run_config.is_some();
        if self.handler.is_some() && routed {
            return Err(StartError::Conflict(
                "a raw handler takes no router, routes or guard settings",
            ));
        }
        let separate_guard_settings = self.api_key.is_some()
            || self.cors_origins.is_some()
            || self.allowed_hosts.is_some()
            || self.run_config.is_some();
        if self.router.is_some() && (self.guard.is_some() || separate_guard_settings) {
            return Err(StartError::Conflict(
                "a given router keeps its own guards and takes no guard settings",
            ));
        }
        if self.guard.is_some() && separate_guard_settings {
            return Err(StartError::Conflict(
                "a whole guard config takes no separate guard settings",
            ));
        }
        let transport = self.transport_config()?;
        let (guard_config, run_config) = self.guard_config()?;
        let temp = match self.config_dir {
            ConfigDir::Temp => Some(TempDir::new("config").map_err(StartError::TempDir)?),
            _ => None,
        };
        let config_dir = match (&self.config_dir, &temp) {
            (ConfigDir::Path(p), _) => Some(p.clone()),
            (_, Some(t)) => Some(t.path().to_path_buf()),
            _ => None,
        };
        let (log, capture) = FifoLog::capture();
        let driver = match self.engine {
            Some(factory) => {
                let settings = self.turn_settings.unwrap_or_else(|| TurnSettings {
                    queue_ping: queue_ping_interval_from(
                        self.env.get(names::QUEUE_PING_S).map(String::as_str),
                    ),
                    ..TurnSettings::default()
                });
                let observer = self.observer.unwrap_or_else(|| Arc::new(NoObserver));
                let fifo = EngineFifo::with_log(self.capacity, log.clone());
                let driver = TurnDriver::start(factory, fifo, settings, observer, log)
                    .await
                    .map_err(StartError::Engine)?;
                Some(driver)
            }
            None => None,
        };
        let parts = Parts {
            driver: driver.clone(),
            tokenizer: Arc::new(ByteTokenizer::new()),
            env: Arc::new(self.env),
            clock: self.clock,
            config_dir,
            run_config,
            transport,
        };
        let (handler, router): (Arc<dyn Handler>, Option<Arc<Router>>) = match self.handler {
            Some(handler) => (handler, None),
            None => {
                let mut router = self.router.unwrap_or_else(|| Router::new(guard_config));
                for (route, source) in self.routes {
                    let handler = match source {
                        RouteSource::Handler(h) => h,
                        RouteSource::Factory(make) => make(&parts),
                    };
                    router.register(route, handler);
                }
                let router = Arc::new(router);
                let handler: Arc<dyn Handler> = router.clone();
                (handler, Some(router))
            }
        };
        let listener = match bind(SocketAddr::new(self.bind, 0), transport) {
            Ok(listener) => listener,
            Err(e) => {
                if let Some(d) = &driver {
                    d.close().await;
                }
                return Err(StartError::Bind(e));
            }
        };
        let addr = match listener.local_addr() {
            Ok(addr) => addr,
            Err(e) => {
                if let Some(d) = &driver {
                    d.close().await;
                }
                return Err(StartError::Bind(e));
            }
        };
        let backlog = listener.backlog();
        let (stop, stopped) = oneshot::channel::<()>();
        let task = tokio::spawn(listener.serve(handler, async move {
            let _ = stopped.await;
        }));
        Ok(TestServer {
            addr,
            backlog,
            router,
            parts,
            log: capture,
            stop: Some(stop),
            task: Some(task),
            _temp: temp,
        })
    }
}

/// A running test server. Dropping it stops the listener; [`TestServer::stop`] also waits
/// for it and closes the engine.
pub struct TestServer {
    /// The bound address (`127.0.0.1:<port>` by default).
    pub addr: SocketAddr,
    /// The listen backlog in force.
    pub backlog: u32,
    router: Option<Arc<Router>>,
    parts: Parts,
    log: LogCapture,
    stop: Option<oneshot::Sender<()>>,
    task: Option<JoinHandle<JoinSet<()>>>,
    _temp: Option<TempDir>,
}

impl fmt::Debug for TestServer {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("TestServer")
            .field("addr", &self.addr)
            .field("backlog", &self.backlog)
            .field("parts", &self.parts)
            .finish_non_exhaustive()
    }
}

impl TestServer {
    /// The settings of a new server.
    pub fn builder() -> TestServerBuilder {
        TestServerBuilder::default()
    }

    /// Serves `router` on a loopback port, with nothing else: the API-03 tests' server.
    /// Panics when the listener cannot be bound.
    pub async fn with_router(router: Router) -> Self {
        match Self::builder().router(router).start().await {
            Ok(server) => server,
            Err(e) => panic!("test server: {e}"),
        }
    }

    /// Serves every request with `handler` on a loopback port, with these transport
    /// settings. Panics when the listener cannot be bound.
    pub async fn with_handler(handler: Arc<dyn Handler>, config: TransportConfig) -> Self {
        match Self::builder()
            .handler(handler)
            .transport(config)
            .start()
            .await
        {
            Ok(server) => server,
            Err(e) => panic!("test server: {e}"),
        }
    }

    /// The bound port.
    pub fn port(&self) -> u16 {
        self.addr.port()
    }

    /// `host:port` as a client puts it in `Host` (`127.0.0.1:<port>`; IPv6 in brackets).
    pub fn host(&self) -> String {
        self.addr.to_string()
    }

    /// `http://host:port`, the donor's `base`.
    pub fn base_url(&self) -> String {
        format!("http://{}", self.addr)
    }

    /// The router, unless the server serves a raw handler.
    pub fn router(&self) -> Option<&Arc<Router>> {
        self.router.as_ref()
    }

    /// The turn driver, when the server was given an engine.
    pub fn driver(&self) -> Option<&TurnDriver> {
        self.parts.driver.as_ref()
    }

    /// The server's parts, as handler factories saw them.
    pub fn parts(&self) -> &Parts {
        &self.parts
    }

    /// The byte tokenizer.
    pub fn tokenizer(&self) -> &ByteTokenizer {
        &self.parts.tokenizer
    }

    /// The configuration folder, when one was asked for.
    pub fn config_dir(&self) -> Option<&Path> {
        self.parts.config_dir.as_deref()
    }

    /// The lines the engine FIFO and driver logged so far.
    pub fn log_lines(&self) -> Vec<String> {
        self.log.lines()
    }

    /// Sends `request`, adding `Host: <host>` when it has none.
    pub async fn send(&self, request: RawRequest) -> RawResponse {
        let request = if request.has_header("host") {
            request
        } else {
            request.header("Host", &self.host())
        };
        request.send(self.addr).await
    }

    /// Sends one request: `method path`, a `Host` of [`host`](Self::host) unless `headers`
    /// has one, the headers in order, and the body with its `Content-Length`.
    pub async fn call(
        &self,
        method: &str,
        path: &str,
        headers: &[(&str, &str)],
        body: Option<&[u8]>,
    ) -> RawResponse {
        let mut request = RawRequest::new(method, path);
        if !headers.iter().any(|(k, _)| k.eq_ignore_ascii_case("host")) {
            request = request.header("Host", &self.host());
        }
        for (k, v) in headers {
            request = request.header(k, v);
        }
        if let Some(body) = body {
            request = request.body(body);
        }
        request.send(self.addr).await
    }

    /// A `GET` of `path`. A redirect is returned as it is, not followed (the donor's
    /// `WebApp.get` goes through `urllib`, which follows it: see
    /// [`get_following`](Self::get_following)).
    pub async fn get(&self, path: &str, headers: &[(&str, &str)]) -> RawResponse {
        self.call("GET", path, headers, None).await
    }

    /// A `GET` of `path` that follows redirects on this server, as `urllib.request.urlopen`
    /// in the donor's `WebApp.get` does: a 301, 302, 303, 307 or 308 answer with a
    /// `Location` that is a path (`/...`) or this server's [`base_url`](Self::base_url)
    /// followed by a path is requested again with `GET` and the same headers, up to
    /// urllib's 10 redirects. Returns the last answer: the first one that is not such a
    /// redirect, or the redirect that points elsewhere. Panics on the eleventh redirect, as
    /// urllib raises `HTTPError` then. urllib's own extra headers (`Accept-Encoding`,
    /// `User-Agent`, `Connection: close`) are not added.
    ///
    /// Behavior reference: project-maya serve/test_server.py:1683-1689 and 1754 at
    /// 7e68a30f.
    pub async fn get_following(&self, path: &str, headers: &[(&str, &str)]) -> RawResponse {
        const MAX_REDIRECTS: usize = 10;
        let base = self.base_url();
        let mut target = path.to_owned();
        for _ in 0..=MAX_REDIRECTS {
            let r = self.get(&target, headers).await;
            if !matches!(r.status, 301 | 302 | 303 | 307 | 308) {
                return r;
            }
            let Some(location) = r.header("Location") else {
                return r;
            };
            let next = if location.starts_with('/') && !location.starts_with("//") {
                location.to_owned()
            } else if let Some(rest) = location.strip_prefix(base.as_str()) {
                if rest.is_empty() {
                    String::from("/")
                } else if rest.starts_with('/') {
                    rest.to_owned()
                } else {
                    return r;
                }
            } else {
                return r;
            };
            target = next;
        }
        panic!("more than {MAX_REDIRECTS} redirects from {path}");
    }

    /// A JSON `POST` (`Content-Type: application/json` first) of `body`.
    pub async fn post_json(&self, path: &str, headers: &[(&str, &str)], body: &str) -> RawResponse {
        let mut all = vec![("Content-Type", "application/json")];
        all.extend_from_slice(headers);
        self.call("POST", path, &all, Some(body.as_bytes())).await
    }

    /// Writes `bytes` as they are and reads the answer.
    pub async fn exchange(&self, bytes: &[u8]) -> RawResponse {
        raw::exchange(self.addr, bytes).await
    }

    /// Opens an event stream: writes `bytes` and reads the head.
    pub async fn sse(&self, bytes: &[u8]) -> SseReader {
        SseReader::open(self.addr, bytes).await
    }

    /// Stops accepting, closes the engine, and returns the connections still in flight.
    pub async fn stop(mut self) -> JoinSet<()> {
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
        let set = match self.task.take() {
            Some(task) => match task.await {
                Ok(set) => set,
                Err(e) => panic!("serve task: {e}"),
            },
            None => JoinSet::new(),
        };
        if let Some(driver) = &self.parts.driver {
            driver.close().await;
        }
        set
    }
}

impl Drop for TestServer {
    fn drop(&mut self) {
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
    }
}
