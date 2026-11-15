//! Owned by API-03. The route table in the donor's dispatch order, with handler slots.
//!
//! [`Router`] is the transport's [`Handler`]. For each request it runs the guards of
//! [`crate::guard`] in the donor's order, finds the route in [`ROUTES`], and hands the
//! request to the [`RouteHandler`] registered for that route's [`Route`] slot. Later
//! packages register their handlers at start ([`Router::register`]); a slot with no handler
//! answers as an unknown route (404 `{"error": {"message": "not found"}}`) after its
//! guards, except `/web`, whose redirect is built in.
//!
//! # Order per method
//!
//! Every request the router sees first passes the `Host` allowlist (deviation SEC-1.1): a
//! refused `Host` is 403 `permission_error` before anything else, and its answer carries no
//! CORS header. The transport asks the router's [`Handler::early_refusal`] as soon as it has
//! the head, so the same 403 also comes before the transport's own 501 for a method it does
//! not serve and its 400 for conflicting framing (deviation P-2). Only the 431 header-limit
//! pages, and the 400, 414 and 505 pages of the request line, are answered without the
//! allowlist: the transport has no usable headers there. They carry no CORS header for a
//! refused `Host` ([`Guard::cors_headers`]).
//!
//! - **OPTIONS** (any path): the CORS preflight, no key (the donor's `do_OPTIONS`).
//! - **GET**: the foreign-page check (deviation SEC-1.2: the donor checks `Origin` only on
//!   POST and DELETE), then the route in [`ROUTES`] order; a route marked
//!   [`KeyCheck::Router`] then asks for the key; an unknown path is 404 with no key asked.
//! - **POST**: the key, then the foreign-page check (the donor's order), then the JSON
//!   content type (deviation SEC-1.3; the attachment route keeps its own raw-bytes check),
//!   then the route; a mutating admin or ops route then needs a loopback client or a
//!   configured key (deviation SEC-1.4). Routes marked [`BodyMode::Json`], and every unknown
//!   path, have their body read and parsed by the router (a body that is not a JSON object
//!   is 400), and an unknown path is then 404. A SEC-1.4 refusal is answered after the body
//!   is read, as the donor reads the body before its own gates, so that the answer is not
//!   lost to a reset over an unread body.
//! - **DELETE**: the foreign-page check first (the donor's order), then `/v1/responses/*`
//!   (whose handler asks for the key itself; matched on the raw path before `?`, trailing
//!   slashes kept, as the donor's `do_DELETE` does, so `/v1/responses/` reaches it),
//!   `/api/delete` (key, then SEC-1.4), and any other path asks for the key and is 404.
//!
//! The transport answers other methods with 501 before the router is called.
//!
//! # Paths
//!
//! Routes match [`RequestHead::route_path`]: the query dropped and trailing slashes removed,
//! so `/` is `""` and `/v1/messages/?beta=true` is `/v1/messages`. The CORS decision reads
//! the raw path instead, as the donor's `_cors_allow` does.
//!
//! Behavior reference: project-maya serve/server.py:5923-5933 (`do_DELETE`), 5934-6139
//! (`do_GET`), 6160-6297 (`do_POST`) and 5799-5809 (`do_OPTIONS`) at 7e68a30f.

use std::collections::HashMap;
use std::sync::{Arc, RwLock};

use console_pyjson::loads::loads_bytes;
use serde_json::{Map, Value};

use crate::error::ApiError;
use crate::guard::{
    is_json_content_type, Guard, GuardConfig, Refusal, HOST_REFUSED_MESSAGE, LOCAL_ONLY_MESSAGE,
    MODEL_MANAGE_LOCAL_ONLY_MESSAGE,
};
use crate::transport::{BodyError, Exchange, Handler, HandlerFuture, RequestHead};

/// The 400 message of a POST body that parses but is not a JSON object.
///
/// Behavior reference: project-maya serve/server.py:6245-6246 at 7e68a30f.
pub const NOT_AN_OBJECT: &str = "the request body must be a JSON object";

/// A handler slot: the routes one handler serves. A handler that serves several paths sees
/// the matched path in [`RouteRequest::path`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Route {
    /// `GET /models/sse` (llama.cpp's model state stream; its handler asks for the key).
    ModelsSse,
    /// `GET /api/tags`, `/api/ps`, `/api/version`, `/api/catalog`, `/api/pull/status`.
    OllamaGet,
    /// `GET` and `DELETE /v1/responses/<id>[/input_items]` (its handler asks for the key).
    ResponseResource,
    /// `GET /fonts/<name>`: 404 when no handler is registered (BRAND-2.4 ships no font).
    Fonts,
    /// `GET /web`: the built-in redirect to the page one level up.
    WebRedirect,
    /// `GET /web/<file>`: the dashboard's files.
    WebAsset,
    /// `GET /metrics`.
    Metrics,
    /// `GET /metrics/prometheus`.
    MetricsPrometheus,
    /// `GET /settings`.
    SettingsGet,
    /// `GET /mcp`.
    Mcp,
    /// `GET /`: the dashboard page.
    Index,
    /// `GET /health`.
    Health,
    /// `GET /api/context`.
    ContextGet,
    /// `GET /api/thinking-budget`.
    ThinkingBudgetGet,
    /// `GET /api/port`.
    PortGet,
    /// `GET /api/turbo`.
    TurboGet,
    /// `GET /api/models`.
    ModelsInfo,
    /// `GET /api/savings`.
    Savings,
    /// `GET /api/update`.
    UpdateGet,
    /// `GET /api/report`.
    Report,
    /// `GET /status`.
    Status,
    /// `GET /v1/models` and `GET /models`.
    Models,
    /// `GET /props`.
    Props,
    /// `GET /slots`.
    Slots,
    /// `GET /v1/status`.
    V1Status,
    /// `GET /v1/strata/stream`.
    StrataStream,
    /// `POST /models/load` and `POST /models/unload`.
    LlamacppModels,
    /// `POST /v1/responses/<id>/cancel`.
    ResponseCancel,
    /// `POST /api/show`, `/api/pull`, `/api/pull/cancel`, `/api/delete`, `/api/chat`,
    /// `/api/generate`, and `DELETE /api/delete`.
    OllamaPost,
    /// `POST /settings`.
    SettingsPost,
    /// `POST /attach` and `POST /pdf`.
    Attach,
    /// `POST /v1/strata/cancel`.
    StrataCancel,
    /// `POST /api/context`.
    ContextPost,
    /// `POST /api/port`.
    PortPost,
    /// `POST /api/thinking-budget`.
    ThinkingBudgetPost,
    /// `POST /api/update`.
    UpdatePost,
    /// `POST /api/turbo`.
    TurboPost,
    /// `POST /api/models/settings`, `/api/models/switch`, `/api/models/delete`,
    /// `/api/models/leftovers`.
    ModelsAdmin,
    /// `POST /api/savings/reset`.
    SavingsReset,
    /// `POST /api/savings/prices`.
    SavingsPrices,
    /// `POST /api/tokens` (body parsed by the router).
    Tokens,
    /// `POST /tokenize` (body parsed by the router).
    Tokenize,
    /// `POST /detokenize` (body parsed by the router).
    Detokenize,
    /// `POST /v1/chat/completions` (body parsed by the router).
    ChatCompletions,
    /// `POST /v1/responses` (body parsed by the router).
    Responses,
    /// `POST /v1/messages` (body parsed by the router).
    Messages,
}

/// How a route's path is matched against [`RequestHead::route_path`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Pattern {
    /// The whole path.
    Exact(&'static str),
    /// Any path starting with the text.
    Prefix(&'static str),
    /// Any path starting with the first text and ending with the second.
    PrefixSuffix(&'static str, &'static str),
}

impl Pattern {
    /// Whether `path` (a route path) matches.
    pub fn matches(self, path: &str) -> bool {
        match self {
            Pattern::Exact(p) => path == p,
            Pattern::Prefix(p) => path.starts_with(p),
            Pattern::PrefixSuffix(p, s) => path.starts_with(p) && path.ends_with(s),
        }
    }
}

/// Who asks for the API key on a route.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum KeyCheck {
    /// Nobody: the route is open (`/`, `/health`, `/web/*`, `/fonts/*`, `/web`).
    Open,
    /// The router, before the handler runs.
    Router,
    /// The handler, where the donor's handler asks (`/models/sse` after its management
    /// check; `/v1/responses/*` first thing). Handlers call [`Guard::check_key`].
    Handler,
}

/// The extra gate of a mutating admin or ops route (deviation SEC-1.4).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Gate {
    /// None.
    None,
    /// A loopback client or a configured key; else 403 `permission_error`
    /// [`LOCAL_ONLY_MESSAGE`].
    LocalOrKey,
    /// The same rule for the model-management routes, answered with the donor's own
    /// 403 `{"error": "set an API key to download, delete or switch models over the
    /// network"}`.
    ModelManage,
}

/// How a route's body is handled.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BodyMode {
    /// No body read by the router (every GET and DELETE route).
    None,
    /// A JSON POST route whose handler reads the body itself.
    Handler,
    /// A JSON POST route whose body the router reads and parses: the handler gets the
    /// object in [`RouteRequest::body`].
    Json,
    /// A POST route that takes raw bytes (`/attach`, `/pdf`): exempt from the router's
    /// JSON content type check; its handler applies [`Guard::attach_page`].
    Raw,
}

/// One row of the dispatch table.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RouteSpec {
    /// `GET`, `POST` or `DELETE`.
    pub method: &'static str,
    /// The path pattern.
    pub pattern: Pattern,
    /// The handler slot.
    pub route: Route,
    /// Who asks for the key (for POST the router always asks first).
    pub key: KeyCheck,
    /// The SEC-1.4 gate.
    pub gate: Gate,
    /// The body handling.
    pub body: BodyMode,
}

const fn get(pattern: Pattern, route: Route, key: KeyCheck) -> RouteSpec {
    RouteSpec {
        method: "GET",
        pattern,
        route,
        key,
        gate: Gate::None,
        body: BodyMode::None,
    }
}

const fn post(pattern: Pattern, route: Route, gate: Gate, body: BodyMode) -> RouteSpec {
    RouteSpec {
        method: "POST",
        pattern,
        route,
        key: KeyCheck::Router,
        gate,
        body,
    }
}

const fn delete(pattern: Pattern, route: Route, key: KeyCheck, gate: Gate) -> RouteSpec {
    RouteSpec {
        method: "DELETE",
        pattern,
        route,
        key,
        gate,
        body: BodyMode::None,
    }
}

use BodyMode as B;
use Gate as G;
use KeyCheck as K;
use Pattern::{Exact, Prefix, PrefixSuffix};
use Route as R;

/// The dispatch table, per method in the donor's order: the first row whose method and
/// pattern match wins. A reviewer can read it side by side with `do_GET` (server.py
/// 5934-6139), `do_POST` (6160-6297) and `do_DELETE` (5923-5933) at 7e68a30f.
pub const ROUTES: &[RouteSpec] = &[
    // do_GET, in order.
    get(Exact("/models/sse"), R::ModelsSse, K::Handler),
    get(Exact("/api/tags"), R::OllamaGet, K::Router),
    get(Exact("/api/ps"), R::OllamaGet, K::Router),
    get(Exact("/api/version"), R::OllamaGet, K::Router),
    get(Exact("/api/catalog"), R::OllamaGet, K::Router),
    get(Exact("/api/pull/status"), R::OllamaGet, K::Router),
    get(Prefix("/v1/responses/"), R::ResponseResource, K::Handler),
    get(Prefix("/fonts/"), R::Fonts, K::Open),
    get(Exact("/web"), R::WebRedirect, K::Open),
    get(Prefix("/web/"), R::WebAsset, K::Open),
    get(Exact("/metrics"), R::Metrics, K::Router),
    get(
        Exact("/metrics/prometheus"),
        R::MetricsPrometheus,
        K::Router,
    ),
    get(Exact("/settings"), R::SettingsGet, K::Router),
    get(Exact("/mcp"), R::Mcp, K::Router),
    get(Exact(""), R::Index, K::Open),
    get(Exact("/health"), R::Health, K::Open),
    get(Exact("/api/context"), R::ContextGet, K::Router),
    get(
        Exact("/api/thinking-budget"),
        R::ThinkingBudgetGet,
        K::Router,
    ),
    get(Exact("/api/port"), R::PortGet, K::Router),
    get(Exact("/api/turbo"), R::TurboGet, K::Router),
    get(Exact("/api/models"), R::ModelsInfo, K::Router),
    get(Exact("/api/savings"), R::Savings, K::Router),
    get(Exact("/api/update"), R::UpdateGet, K::Router),
    get(Exact("/api/report"), R::Report, K::Router),
    get(Exact("/status"), R::Status, K::Router),
    get(Exact("/v1/models"), R::Models, K::Router),
    get(Exact("/models"), R::Models, K::Router),
    get(Exact("/props"), R::Props, K::Router),
    get(Exact("/slots"), R::Slots, K::Router),
    get(Exact("/v1/status"), R::V1Status, K::Router),
    get(Exact("/v1/strata/stream"), R::StrataStream, K::Router),
    // do_POST, in order (the key and the foreign-page check come first).
    post(
        Exact("/models/load"),
        R::LlamacppModels,
        G::ModelManage,
        B::Handler,
    ),
    post(
        Exact("/models/unload"),
        R::LlamacppModels,
        G::ModelManage,
        B::Handler,
    ),
    post(
        PrefixSuffix("/v1/responses/", "/cancel"),
        R::ResponseCancel,
        G::None,
        B::Handler,
    ),
    post(Exact("/api/show"), R::OllamaPost, G::None, B::Handler),
    post(
        Exact("/api/pull"),
        R::OllamaPost,
        G::ModelManage,
        B::Handler,
    ),
    post(
        Exact("/api/pull/cancel"),
        R::OllamaPost,
        G::ModelManage,
        B::Handler,
    ),
    post(
        Exact("/api/delete"),
        R::OllamaPost,
        G::ModelManage,
        B::Handler,
    ),
    post(Exact("/api/chat"), R::OllamaPost, G::None, B::Handler),
    post(Exact("/api/generate"), R::OllamaPost, G::None, B::Handler),
    post(
        Exact("/settings"),
        R::SettingsPost,
        G::LocalOrKey,
        B::Handler,
    ),
    post(Exact("/attach"), R::Attach, G::None, B::Raw),
    post(Exact("/pdf"), R::Attach, G::None, B::Raw),
    post(
        Exact("/v1/strata/cancel"),
        R::StrataCancel,
        G::None,
        B::Handler,
    ),
    post(
        Exact("/api/context"),
        R::ContextPost,
        G::LocalOrKey,
        B::Handler,
    ),
    post(Exact("/api/port"), R::PortPost, G::LocalOrKey, B::Handler),
    post(
        Exact("/api/thinking-budget"),
        R::ThinkingBudgetPost,
        G::LocalOrKey,
        B::Handler,
    ),
    post(
        Exact("/api/update"),
        R::UpdatePost,
        G::LocalOrKey,
        B::Handler,
    ),
    post(Exact("/api/turbo"), R::TurboPost, G::LocalOrKey, B::Handler),
    post(
        Exact("/api/models/settings"),
        R::ModelsAdmin,
        G::LocalOrKey,
        B::Handler,
    ),
    post(
        Exact("/api/models/switch"),
        R::ModelsAdmin,
        G::LocalOrKey,
        B::Handler,
    ),
    post(
        Exact("/api/models/delete"),
        R::ModelsAdmin,
        G::LocalOrKey,
        B::Handler,
    ),
    post(
        Exact("/api/models/leftovers"),
        R::ModelsAdmin,
        G::LocalOrKey,
        B::Handler,
    ),
    post(
        Exact("/api/savings/reset"),
        R::SavingsReset,
        G::LocalOrKey,
        B::Handler,
    ),
    post(
        Exact("/api/savings/prices"),
        R::SavingsPrices,
        G::LocalOrKey,
        B::Handler,
    ),
    // After the body is read and parsed as an object.
    post(Exact("/api/tokens"), R::Tokens, G::None, B::Json),
    post(Exact("/tokenize"), R::Tokenize, G::None, B::Json),
    post(Exact("/detokenize"), R::Detokenize, G::None, B::Json),
    post(
        Exact("/v1/chat/completions"),
        R::ChatCompletions,
        G::None,
        B::Json,
    ),
    post(Exact("/v1/responses"), R::Responses, G::None, B::Json),
    post(Exact("/v1/messages"), R::Messages, G::None, B::Json),
    // do_DELETE, in order (the foreign-page check comes first).
    delete(
        Prefix("/v1/responses/"),
        R::ResponseResource,
        K::Handler,
        G::None,
    ),
    delete(
        Exact("/api/delete"),
        R::OllamaPost,
        K::Router,
        G::ModelManage,
    ),
];

/// The first row of [`ROUTES`] for `method` whose pattern matches `path` (a route path).
pub fn lookup(method: &str, path: &str) -> Option<&'static RouteSpec> {
    ROUTES
        .iter()
        .find(|spec| spec.method == method && spec.pattern.matches(path))
}

/// One routed request, as a [`RouteHandler`] receives it.
#[derive(Debug)]
pub struct RouteRequest {
    /// The connection: head, body (unless the router read it), answer and client watch.
    pub exchange: Exchange,
    /// The matched slot.
    pub route: Route,
    /// The request's route path ([`RequestHead::route_path`]). For `DELETE /v1/responses/`
    /// it is `/v1/responses`; that handler reads the raw path, as the donor's does.
    pub path: String,
    /// For [`BodyMode::Json`] routes, the parsed body object; otherwise `None` and the body
    /// is still unread.
    pub body: Option<Map<String, Value>>,
    /// The guards in force for this request ([`Guard::check_key`],
    /// [`Guard::response_owner`], [`Guard::own_page`], [`Guard::attach_page`],
    /// [`Guard::local_or_keyed`]).
    pub guard: Arc<Guard>,
}

/// What a later package registers for a [`Route`]: one trait object per slot.
pub trait RouteHandler: Send + Sync + 'static {
    /// Serves one request that passed the router's guards for its route. The connection
    /// closes when the future ends; a handler that writes nothing sends no answer.
    fn serve(&self, request: RouteRequest) -> HandlerFuture<'_>;
}

/// What the guards decided before any body is read.
enum Decision {
    Refuse(Refusal),
    /// SEC-1.4: refuse, after reading the body as the donor's gated routes do.
    RefuseAfterBody(Refusal),
    /// SEC-1.3: refuse with 415, after reading the body as the donor's `_own_page` routes do.
    NotJson,
    Preflight(crate::guard::Preflight),
    NotFound,
    /// An unknown POST path: the body is read and parsed, then 404.
    PostFallback,
    Dispatch(&'static RouteSpec),
}

/// The router: the dispatch table, the guards and the registered handlers.
pub struct Router {
    guard: RwLock<Arc<Guard>>,
    handlers: HashMap<Route, Arc<dyn RouteHandler>>,
}

impl std::fmt::Debug for Router {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let mut routes: Vec<String> = self.handlers.keys().map(|r| format!("{r:?}")).collect();
        routes.sort();
        f.debug_struct("Router")
            .field("guard", &self.guard())
            .field("registered", &routes)
            .finish()
    }
}

impl Router {
    /// A router with the guards of `config` and no handler registered.
    pub fn new(config: GuardConfig) -> Self {
        Self {
            guard: RwLock::new(Arc::new(Guard::new(config))),
            handlers: HashMap::new(),
        }
    }

    /// Registers `handler` for `route`, returning the handler it replaces.
    pub fn register(
        &mut self,
        route: Route,
        handler: Arc<dyn RouteHandler>,
    ) -> Option<Arc<dyn RouteHandler>> {
        self.handlers.insert(route, handler)
    }

    /// [`register`](Self::register) in builder form.
    pub fn with(mut self, route: Route, handler: Arc<dyn RouteHandler>) -> Self {
        self.handlers.insert(route, handler);
        self
    }

    /// Whether a handler is registered for `route`.
    pub fn is_registered(&self, route: Route) -> bool {
        self.handlers.contains_key(&route)
    }

    /// The guards in force.
    pub fn guard(&self) -> Arc<Guard> {
        match self.guard.read() {
            Ok(g) => Arc::clone(&g),
            Err(poisoned) => Arc::clone(&poisoned.into_inner()),
        }
    }

    /// Replaces the guards' configuration (for example after the API key setting
    /// changes). Requests already past their guards are not affected.
    pub fn replace_guard(&self, config: GuardConfig) {
        let next = Arc::new(Guard::new(config));
        match self.guard.write() {
            Ok(mut g) => *g = next,
            Err(poisoned) => *poisoned.into_inner() = next,
        }
    }

    fn decide(guard: &Guard, head: &RequestHead, peer: std::net::IpAddr) -> Decision {
        if let Err(refusal) = guard.check_host(head) {
            return Decision::Refuse(refusal);
        }
        let path = head.route_path();
        match head.method() {
            "OPTIONS" => Decision::Preflight(guard.preflight(head)),
            "GET" => {
                if let Err(refusal) = guard.check_foreign_page(head) {
                    return Decision::Refuse(refusal);
                }
                match lookup("GET", path) {
                    None => Decision::NotFound,
                    Some(spec) => {
                        if spec.key == KeyCheck::Router && !guard.authorized(head) {
                            return Decision::Refuse(Refusal::auth());
                        }
                        Decision::Dispatch(spec)
                    }
                }
            }
            "POST" => {
                if let Err(refusal) = guard.check_key(head) {
                    return Decision::Refuse(refusal);
                }
                if let Err(refusal) = guard.check_foreign_page(head) {
                    return Decision::Refuse(refusal);
                }
                let spec = lookup("POST", path);
                let raw = spec.is_some_and(|s| s.body == BodyMode::Raw);
                if !raw && !is_json_content_type(head.headers()) {
                    return Decision::NotJson;
                }
                match spec {
                    None => Decision::PostFallback,
                    Some(spec) => match gate_refusal(guard, spec.gate, peer) {
                        Some(refusal) => Decision::RefuseAfterBody(refusal),
                        None => Decision::Dispatch(spec),
                    },
                }
            }
            "DELETE" => {
                if let Err(refusal) = guard.check_foreign_page(head) {
                    return Decision::Refuse(refusal);
                }
                let spec = lookup_delete(head.path());
                let key_by_router = spec.is_none_or(|s| s.key == KeyCheck::Router);
                if key_by_router && !guard.authorized(head) {
                    return Decision::Refuse(Refusal::auth());
                }
                match spec {
                    None => Decision::NotFound,
                    Some(spec) => match gate_refusal(guard, spec.gate, peer) {
                        Some(refusal) => Decision::Refuse(refusal),
                        None => Decision::Dispatch(spec),
                    },
                }
            }
            // The transport answers every other method with 501 before calling the router.
            _ => Decision::NotFound,
        }
    }

    async fn serve(&self, mut exchange: Exchange) {
        let guard = self.guard();
        let decision = Self::decide(&guard, exchange.head(), exchange.peer_addr().ip());
        match decision {
            Decision::Refuse(refusal) => {
                let _ = refusal.answer(exchange.responder()).await;
            }
            Decision::RefuseAfterBody(refusal) => {
                refuse_after_body(&mut exchange, &refusal).await;
            }
            Decision::NotJson => {
                refuse_after_body(&mut exchange, &Refusal::not_json()).await;
            }
            Decision::Preflight(preflight) => {
                let headers: Vec<(&str, &str)> = preflight
                    .headers
                    .iter()
                    .map(|(k, v)| (k.as_str(), v.as_str()))
                    .collect();
                let _ = exchange
                    .responder()
                    .send(preflight.status, &headers, b"")
                    .await;
            }
            Decision::NotFound => {
                let _ = exchange.responder().error(&ApiError::NotFound).await;
            }
            Decision::PostFallback => {
                if read_object(&mut exchange).await.is_some() {
                    let _ = exchange.responder().error(&ApiError::NotFound).await;
                }
            }
            Decision::Dispatch(spec) => {
                let body = if spec.body == BodyMode::Json {
                    match read_object(&mut exchange).await {
                        Some(map) => Some(map),
                        None => return,
                    }
                } else {
                    None
                };
                let path = exchange.head().route_path().to_owned();
                match self.handlers.get(&spec.route) {
                    Some(handler) => {
                        let request = RouteRequest {
                            exchange,
                            route: spec.route,
                            path,
                            body,
                            guard,
                        };
                        handler.serve(request).await;
                    }
                    None => default_answer(spec.route, &mut exchange).await,
                }
            }
        }
    }
}

/// The DELETE row for a request with the raw path `raw_path`: `/v1/responses/*` when the
/// raw path before `?` starts with `/v1/responses/` (trailing slashes kept, so
/// `/v1/responses/` and `/v1/responses/?a=1` reach its handler), else the row
/// [`lookup`] finds for the route path.
///
/// Behavior reference: project-maya serve/server.py:5923-5932 at 7e68a30f.
pub fn lookup_delete(raw_path: &str) -> Option<&'static RouteSpec> {
    let before_query = raw_path.split('?').next().unwrap_or("");
    if before_query.starts_with("/v1/responses/") {
        return ROUTES
            .iter()
            .find(|spec| spec.method == "DELETE" && spec.route == Route::ResponseResource);
    }
    lookup("DELETE", before_query.trim_end_matches('/'))
}

/// Answers `refusal` after reading the body, as the donor's routes read the body before
/// their own checks, so that the answer is not lost to a reset over an unread body. A body
/// that cannot be read is answered with its own error; a client that is gone gets nothing.
async fn refuse_after_body(exchange: &mut Exchange, refusal: &Refusal) {
    match exchange.read_body().await {
        Ok(_) => {
            let _ = refusal.answer(exchange.responder()).await;
        }
        Err(BodyError::Refused(e)) => {
            let _ = exchange.responder().error(&e).await;
        }
        Err(_) => {}
    }
}

/// The SEC-1.4 refusal of `gate` for a client at `peer`, if any.
fn gate_refusal(guard: &Guard, gate: Gate, peer: std::net::IpAddr) -> Option<Refusal> {
    if gate == Gate::None || guard.local_or_keyed(peer) {
        return None;
    }
    Some(Refusal::Api(match gate {
        Gate::ModelManage => ApiError::plain(403, MODEL_MANAGE_LOCAL_ONLY_MESSAGE),
        _ => ApiError::permission(LOCAL_ONLY_MESSAGE),
    }))
}

/// Reads the body and parses it as the donor's `json.loads(raw_ or b"{}")`, requiring an
/// object. On failure the error is answered (or the client is gone) and `None` returned.
///
/// Behavior reference: project-maya serve/server.py:6241-6246 and 6283-6288 at 7e68a30f.
async fn read_object(exchange: &mut Exchange) -> Option<Map<String, Value>> {
    let raw = match exchange.read_body().await {
        Ok(raw) => raw,
        Err(BodyError::Refused(e)) => {
            let _ = exchange.responder().error(&e).await;
            return None;
        }
        Err(_) => return None,
    };
    let text: &[u8] = if raw.is_empty() { b"{}" } else { &raw };
    let error = match loads_bytes(text) {
        Ok(Value::Object(map)) => return Some(map),
        Ok(_) => ApiError::validation(NOT_AN_OBJECT),
        Err(e) => ApiError::from(e),
    };
    let _ = exchange.responder().error(&error).await;
    None
}

/// The answer of a slot with no handler: the `/web` redirect, else 404.
async fn default_answer(route: Route, exchange: &mut Exchange) {
    if route == Route::WebRedirect {
        let location = web_redirect_location(exchange.head().path());
        let _ = exchange.responder().redirect(&location).await;
    } else {
        let _ = exchange.responder().error(&ApiError::NotFound).await;
    }
}

/// The `Location` of the `/web` redirect: `../` when the raw path ends with `/`, else `./`,
/// followed by the query with its `?`. Relative, so that it works behind a path-prefixed
/// proxy.
///
/// Behavior reference: project-maya serve/server.py:5959-5969 at 7e68a30f.
pub fn web_redirect_location(raw_path: &str) -> String {
    let (before, query) = match raw_path.find('?') {
        Some(at) => (
            raw_path.get(..at).unwrap_or(""),
            raw_path.get(at..).unwrap_or(""),
        ),
        None => (raw_path, ""),
    };
    let up = if before.ends_with('/') { "../" } else { "./" };
    format!("{up}{query}")
}

impl Handler for Router {
    fn handle(&self, exchange: Exchange) -> HandlerFuture<'_> {
        Box::pin(self.serve(exchange))
    }

    /// The donor's `end_headers` override: the CORS headers of this request (none when the
    /// `Host` is refused).
    fn end_headers(&self, head: &RequestHead) -> Vec<(String, String)> {
        self.guard().cors_headers(head)
    }

    /// The `Host` allowlist of deviation SEC-1.1, and nothing else: a refused `Host` is the
    /// same 403 `permission_error` the router answers on a route ([`Guard::check_host`]),
    /// here also before the transport's 501 and P-2 pages. The key, `Origin` and content
    /// type checks stay in the router's dispatch, which checks the `Host` again.
    fn early_refusal(&self, head: &RequestHead) -> Option<ApiError> {
        host_refusal(&self.guard(), head)
    }
}

/// The early answer of a refused `Host`: the error of [`Refusal::host`].
fn host_refusal(guard: &Guard, head: &RequestHead) -> Option<ApiError> {
    if guard.host_allowed(head) {
        None
    } else {
        Some(ApiError::permission(HOST_REFUSED_MESSAGE))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::{IpAddr, Ipv4Addr, SocketAddr};
    use std::time::Duration;

    use tokio::io::{AsyncReadExt, AsyncWriteExt, BufReader};
    use tokio::net::{TcpListener, TcpStream};

    use crate::transport::{Headers, Responder, TransportConfig};

    #[test]
    fn lookup_follows_the_donor_order() {
        let at = |m: &str, p: &str| lookup(m, p).map(|s| s.route);
        assert_eq!(at("GET", "/web"), Some(Route::WebRedirect));
        assert_eq!(at("GET", "/web/app.js"), Some(Route::WebAsset));
        assert_eq!(at("GET", "/fonts/x.woff2"), Some(Route::Fonts));
        assert_eq!(at("GET", "/fonts"), None);
        assert_eq!(at("GET", "/v1/responses"), None);
        assert_eq!(
            at("GET", "/v1/responses/r/input_items"),
            Some(Route::ResponseResource)
        );
        assert_eq!(at("GET", ""), Some(Route::Index));
        assert_eq!(at("GET", "/models"), Some(Route::Models));
        assert_eq!(at("GET", "/v1/strata/cancel"), None);
        assert_eq!(
            at("POST", "/v1/responses/r/cancel"),
            Some(Route::ResponseCancel)
        );
        assert_eq!(at("POST", "/v1/responses/r"), None);
        assert_eq!(at("POST", "/v1/messages"), Some(Route::Messages));
        assert_eq!(at("POST", "/v1/strata/stream"), None);
        assert_eq!(at("DELETE", "/api/delete"), Some(Route::OllamaPost));
        assert_eq!(
            at("DELETE", "/v1/responses/r"),
            Some(Route::ResponseResource)
        );
        assert_eq!(at("DELETE", "/settings"), None);
        assert_eq!(at("PUT", "/v1/models"), None);
    }

    // The donor's do_DELETE (serve/server.py:5926) tests the raw path before `?` for
    // `/v1/responses/`, trailing slashes kept; only `/api/delete` is compared stripped.
    #[test]
    fn delete_matches_responses_on_the_raw_path() {
        let at = |raw: &str| lookup_delete(raw).map(|s| s.route);
        for raw in [
            "/v1/responses/",
            "/v1/responses/?a=1",
            "/v1/responses/r",
            "/v1/responses//",
            "/v1/responses/r/input_items",
        ] {
            assert_eq!(at(raw), Some(Route::ResponseResource), "{raw}");
        }
        assert_eq!(at("/v1/responses"), None);
        assert_eq!(at("/v1/responses?x=/v1/responses/"), None);
        assert_eq!(at("/api/delete"), Some(Route::OllamaPost));
        assert_eq!(at("/api/delete//?x=1"), Some(Route::OllamaPost));
        assert_eq!(at("/settings"), None);
    }

    #[test]
    fn the_table_is_consistent() {
        for spec in ROUTES {
            match spec.method {
                "GET" => {
                    assert_eq!(spec.body, BodyMode::None, "{spec:?}");
                    assert_eq!(spec.gate, Gate::None, "{spec:?}");
                }
                "POST" => {
                    assert_eq!(spec.key, KeyCheck::Router, "{spec:?}");
                    assert_ne!(spec.body, BodyMode::None, "{spec:?}");
                }
                "DELETE" => assert_eq!(spec.body, BodyMode::None, "{spec:?}"),
                other => panic!("unexpected method {other}"),
            }
            // No row is shadowed by an earlier one.
            if let Pattern::Exact(p) = spec.pattern {
                assert_eq!(lookup(spec.method, p), Some(spec), "{spec:?} is shadowed");
            }
        }
        assert_eq!(ROUTES.iter().filter(|s| s.method == "GET").count(), 31);
        assert_eq!(ROUTES.iter().filter(|s| s.method == "POST").count(), 30);
        assert_eq!(ROUTES.iter().filter(|s| s.method == "DELETE").count(), 2);
    }

    // Deviation SEC-1.1: the early refusal is the router's own refusal of a `Host`, and it
    // refuses nothing for an allowed one.
    #[test]
    fn the_early_refusal_is_the_host_refusal() {
        let router = Router::new(GuardConfig::new(IpAddr::V4(Ipv4Addr::LOCALHOST)));
        let head = |host: &str| {
            RequestHead::new(
                "PUT",
                "/v1/models",
                "HTTP/1.1",
                Headers::from_pairs(vec![(String::from("Host"), host.to_owned())]),
            )
        };
        let refused = head("evil.example:8095");
        assert_eq!(
            router.early_refusal(&refused).map(Refusal::Api),
            router.guard().check_host(&refused).err()
        );
        assert_eq!(
            router.early_refusal(&refused).map(|e| e.status()),
            Some(403)
        );
        assert_eq!(router.early_refusal(&head("127.0.0.1:8095")), None);
        assert_eq!(router.early_refusal(&head("localhost")), None);
    }

    #[test]
    fn web_redirects() {
        assert_eq!(web_redirect_location("/web"), "./");
        assert_eq!(web_redirect_location("/web/"), "../");
        assert_eq!(web_redirect_location("/web/?a=1"), "../?a=1");
        assert_eq!(web_redirect_location("/web?a=/"), "./?a=/");
    }

    /// Serves one request through the router with a chosen peer address, as a client on
    /// another computer would reach it (tests stay on loopback sockets).
    async fn exchange_as(router: &Router, peer: IpAddr, request: &[u8]) -> String {
        let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind");
        let addr = listener.local_addr().expect("addr");
        let mut client = TcpStream::connect(addr).await.expect("connect");
        let (conn, _) = listener.accept().await.expect("accept");
        client.write_all(request).await.expect("write");
        let (read, write) = conn.into_split();
        let mut reader = BufReader::new(read);
        // The head is parsed by hand: the transport's parser is private to it.
        let mut head_text = Vec::new();
        loop {
            let mut byte = [0u8; 1];
            reader.read_exact(&mut byte).await.expect("read");
            head_text.push(byte[0]);
            if head_text.ends_with(b"\r\n\r\n") {
                break;
            }
        }
        let text = String::from_utf8(head_text).expect("ascii");
        let mut lines = text.split("\r\n");
        let first: Vec<&str> = lines.next().unwrap_or("").split(' ').collect();
        let pairs = lines
            .filter(|l| !l.is_empty())
            .filter_map(|l| l.split_once(": "))
            .map(|(k, v)| (k.to_owned(), v.to_owned()))
            .collect();
        let head = RequestHead::new(first[0], first[1], first[2], Headers::from_pairs(pairs));
        let extra = router.end_headers(&head);
        let responder = Responder::new(write, Duration::from_secs(5), false, extra);
        let exchange = Exchange::new(
            head,
            reader,
            responder,
            TransportConfig::default(),
            SocketAddr::new(peer, 50000),
            addr,
        );
        router.handle(exchange).await;
        let mut out = Vec::new();
        let _ = client.read_to_end(&mut out).await;
        String::from_utf8_lossy(&out).into_owned()
    }

    fn post(path: &str, extra: &str) -> Vec<u8> {
        format!(
            "POST {path} HTTP/1.1\r\nHost: 127.0.0.1:8095\r\nContent-Type: application/json\r\n\
             Content-Length: 2\r\n{extra}\r\n{{}}"
        )
        .into_bytes()
    }

    fn status(answer: &str) -> u16 {
        answer
            .split(' ')
            .nth(1)
            .and_then(|s| s.parse().ok())
            .unwrap_or(0)
    }

    // Deviation SEC-1.4: a mutating admin or ops route needs a loopback client or a key.
    #[tokio::test]
    async fn admin_routes_need_a_loopback_client_or_a_key() {
        let remote = IpAddr::V4(Ipv4Addr::new(192, 0, 2, 10));
        let local = IpAddr::V4(Ipv4Addr::LOCALHOST);
        let any = IpAddr::V4(Ipv4Addr::UNSPECIFIED);
        let open = Router::new(GuardConfig::new(any));
        for path in [
            "/settings",
            "/api/context",
            "/api/port",
            "/api/thinking-budget",
            "/api/update",
            "/api/turbo",
            "/api/models/settings",
            "/api/models/switch",
            "/api/models/delete",
            "/api/models/leftovers",
            "/api/savings/reset",
            "/api/savings/prices",
        ] {
            let answer = exchange_as(&open, remote, &post(path, "")).await;
            assert_eq!(status(&answer), 403, "{path}: {answer}");
            assert!(answer.ends_with(&format!(
                "{{\"error\": {{\"type\": \"permission_error\", \"message\": \"{LOCAL_ONLY_MESSAGE}\"}}}}"
            )), "{path}: {answer}");
            // From this computer the router lets it through (no handler here: 404).
            assert_eq!(
                status(&exchange_as(&open, local, &post(path, "")).await),
                404,
                "{path}"
            );
        }
        for path in [
            "/models/load",
            "/models/unload",
            "/api/pull",
            "/api/pull/cancel",
            "/api/delete",
        ] {
            let answer = exchange_as(&open, remote, &post(path, "")).await;
            assert_eq!(status(&answer), 403, "{path}");
            assert!(answer.ends_with(&format!(
                "{{\"error\": \"{MODEL_MANAGE_LOCAL_ONLY_MESSAGE}\"}}"
            )));
        }
        // The refusal is answered after the body is read, as the donor reads it before its
        // gates (serve/server.py:5562-5564, 6419-6422): a body of several KB from another
        // computer still gets the whole 403, not a reset.
        let big = format!("{{\"pad\": \"{}\"}}", "x".repeat(6000));
        for path in ["/settings", "/api/pull"] {
            let request = format!(
                "POST {path} HTTP/1.1\r\nHost: 127.0.0.1:8095\r\nContent-Type: application/json\r\n\
                 Content-Length: {}\r\n\r\n{big}",
                big.len()
            );
            let answer = exchange_as(&open, remote, request.as_bytes()).await;
            assert_eq!(status(&answer), 403, "{path}: {answer}");
            let want = if path == "/settings" {
                format!(
                    "{{\"error\": {{\"type\": \"permission_error\", \"message\": \"{LOCAL_ONLY_MESSAGE}\"}}}}"
                )
            } else {
                format!("{{\"error\": \"{MODEL_MANAGE_LOCAL_ONLY_MESSAGE}\"}}")
            };
            assert!(answer.ends_with(&want), "{path}: {answer}");
        }
        let delete = b"DELETE /api/delete HTTP/1.1\r\nHost: 127.0.0.1:8095\r\n\r\n";
        assert_eq!(status(&exchange_as(&open, remote, delete).await), 403);
        assert_eq!(status(&exchange_as(&open, local, delete).await), 404);
        // Other routes stay open to remote clients when no key is set.
        for path in [
            "/v1/chat/completions",
            "/api/show",
            "/api/chat",
            "/v1/strata/cancel",
            "/tokenize",
        ] {
            assert_eq!(
                status(&exchange_as(&open, remote, &post(path, "")).await),
                404,
                "{path}"
            );
        }
        // With a key configured, a valid key opens the admin routes from anywhere.
        let keyed = Router::new(GuardConfig::new(any).with_api_key(&Value::String("k1".into())));
        let with_key = post("/settings", "Authorization: Bearer k1\r\n");
        assert_eq!(status(&exchange_as(&keyed, remote, &with_key).await), 404);
        assert_eq!(
            status(&exchange_as(&keyed, remote, &post("/settings", "")).await),
            401
        );
    }
}
