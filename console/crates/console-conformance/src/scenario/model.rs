//! The scenario types and the loader that checks a parsed document against the format.
//!
//! Checks run in a fixed order, so the same document always yields the same first
//! error: unknown members of an object first (in document order), then its members in
//! the order the schema lists them, then the cross-field rules, and last the
//! substitution tokens of every string.

use serde_json::{Map, Value};

use super::error::{ErrorKind, Result, ScenarioError};
use super::json::{self, Obj};
use super::schema;
use super::subst;
use super::template::{TemplateRef, MAX_TEMPLATE_REF_CHARS};
use super::tokenizer::{byte_level_chars, TokenizerSpec, BYTE_SPECIALS, FIRST_SPECIAL_ID};

/// Limits on everything a scenario sizes. A document past any of them is refused.
pub mod limits {
    /// The largest scenario file, in bytes.
    pub const MAX_SCENARIO_BYTES: usize = 256 * 1024;
    /// The longest `id`, in characters.
    pub const MAX_ID_CHARS: usize = 64;
    /// The longest `description`.
    pub const MAX_DESCRIPTION_CHARS: usize = 1000;
    /// The longest `notes`.
    pub const MAX_NOTES_CHARS: usize = 4000;
    /// The most `donor` entries.
    pub const MAX_DONOR_ENTRIES: usize = 16;
    /// The longest `donor` entry.
    pub const MAX_DONOR_CHARS: usize = 256;
    /// The most script entries of the scripted engine.
    pub const MAX_SCRIPT_ENTRIES: usize = 64;
    /// The most bytes of all scripts together, after repeats are expanded.
    pub const MAX_SCRIPT_BYTES: usize = 1024 * 1024;
    /// The largest `max_context`.
    pub const MAX_CONTEXT: u64 = 16 * 1024 * 1024;
    /// The largest `delay_ms`.
    pub const MAX_DELAY_MS: u64 = 60_000;
    /// The largest `tok_s`.
    pub const MAX_TOK_S: f64 = 1_000_000.0;
    /// The most extra specials or added tokens of a tokenizer.
    pub const MAX_SPECIALS: usize = 1024;
    /// The longest special or added token.
    pub const MAX_SPECIAL_CHARS: usize = 64;
    /// The largest added-token id.
    pub const MAX_TOKEN_ID: u64 = 1 << 20;
    /// The most arguments of a line fake or flags of the server.
    pub const MAX_ARGS: usize = 64;
    /// The longest argument or flag.
    pub const MAX_ARG_CHARS: usize = 1024;
    /// The most environment entries.
    pub const MAX_ENV: usize = 64;
    /// The longest environment name.
    pub const MAX_ENV_NAME_CHARS: usize = 128;
    /// The longest environment value.
    pub const MAX_ENV_VALUE_CHARS: usize = 4096;
    /// The most files in `data_dir`.
    pub const MAX_DATA_FILES: usize = 32;
    /// The longest relative path or glob.
    pub const MAX_PATH_CHARS: usize = 256;
    /// The most steps.
    pub const MAX_STEPS: usize = 256;
    /// The most headers of a request.
    pub const MAX_HEADERS: usize = 64;
    /// The longest header name.
    pub const MAX_HEADER_NAME_CHARS: usize = 256;
    /// The longest header value.
    pub const MAX_HEADER_VALUE_CHARS: usize = 8192;
    /// The longest request method.
    pub const MAX_METHOD_CHARS: usize = 32;
    /// The longest request path.
    pub const MAX_REQUEST_PATH_CHARS: usize = 8192;
    /// The longest raw request or text body.
    pub const MAX_RAW_CHARS: usize = 128 * 1024;
    /// The largest engine step number of a gate.
    pub const MAX_ENGINE_STEP: u64 = 1_000_000;
    /// The largest `disconnect_after_events`.
    pub const MAX_EVENTS: u64 = 1_000_000;
    /// The largest `disconnect_after_bytes`.
    pub const MAX_BYTES: u64 = 64 * 1024 * 1024;
    /// The longest group name or log-line id.
    pub const MAX_NAME_CHARS: usize = 64;
    /// The most file globs or log-line ids observed.
    pub const MAX_OBSERVED: usize = 32;
}

use limits::*;

/// Server command-line flags the harness sets itself; a scenario may not pass them, nor
/// any abbreviation of them: the donor's parser keeps argparse's default
/// `allow_abbrev=True` (serve/server.py:7116 at 7e68a30f), so `--eng` there means
/// `--engine`. See [`is_abbreviation_of`].
pub const HARNESS_FLAGS: &[&str] = &["--port", "--config", "--engine", "--script", "--tokenizer"];

/// The bind-address flag. The harness always binds loopback, so a scenario may pass it
/// (or an abbreviation of it) only with the value [`LOOPBACK_TOKEN`], after `=` or as the
/// next flag; the donor reads it at serve/server.py:7120 and 7166 at 7e68a30f.
pub const HOST_FLAG: &str = "--host";

/// Run-config keys the harness writes from a line engine's spec; a scenario with a line
/// engine may not set them in `server.config`.
pub const HARNESS_CONFIG_KEYS: &[&str] = &["exe", "args", "tokenizer"];

/// The run-config key of the bind address (serve/server.py:7166 at 7e68a30f). For every
/// engine kind, a scenario may set it in `server.config` only to [`LOOPBACK_TOKEN`].
pub const HOST_CONFIG_KEY: &str = "host";

/// The only bind address a scenario may name: the substitution token the harness fills
/// with its loopback address.
pub const LOOPBACK_TOKEN: &str = "{{loopback}}";

/// Environment names the harness sets itself when it starts the server or a line fake
/// from a cleared environment; a scenario may not set them in `server.env` or a line
/// engine's `env`. `FAKE_ENGINE_GATE` names the engine step-gate FIFO.
pub const RESERVED_ENV: &[&str] = &[
    "PATH",
    "HOME",
    "TZ",
    "LC_ALL",
    "LANG",
    "TMPDIR",
    "PULSAR_CONSOLE_VENDOR_DIR",
    "FAKE_ENGINE_GATE",
];

/// Prefixes of environment names a scenario may not set: the harness's `XDG_*`
/// directories, and the dynamic-loader and interpreter variables (`LD_*`, `DYLD_*`,
/// `PYTHON*`) that would load other code into the server or a fake.
pub const RESERVED_ENV_PREFIXES: &[&str] = &["XDG_", "LD_", "DYLD_", "PYTHON"];

/// Whether `name` is a long option that argparse would expand to `full`: it starts with
/// `--`, has at least one character after it, and is `full` or a prefix of it.
pub fn is_abbreviation_of(name: &str, full: &str) -> bool {
    name.len() > 2 && name.starts_with("--") && full.starts_with(name)
}

/// Whether a scenario may not set the environment name `name`.
pub fn is_reserved_env(name: &str) -> bool {
    RESERVED_ENV.contains(&name) || RESERVED_ENV_PREFIXES.iter().any(|p| name.starts_with(p))
}

/// One conformance scenario: an engine, a template, how the server starts, a list of
/// steps and what to observe. Built by [`Scenario::from_json_str`] and its relatives in the
/// parent module; every value has been checked against the format.
#[derive(Debug, Clone, PartialEq)]
pub struct Scenario {
    /// The scenario id: lower-case letters, digits and hyphens; the file stem.
    pub id: String,
    /// One line on what the scenario shows.
    pub description: Option<String>,
    /// The donor test methods whose setup it transcribes, as `file::Class::method`.
    pub donor: Vec<String>,
    /// Free text for the reviewer, for example where the transcription departs from the
    /// donor setup.
    pub notes: Option<String>,
    /// The engine behind the server.
    pub engine: EngineSpec,
    /// The chat template.
    pub template: TemplateRef,
    /// How the server is started.
    pub server: ServerSpec,
    /// What the harness does, in order.
    pub steps: Vec<Step>,
    /// What the harness records.
    pub observe: Observe,
    /// The document as read, kept so that [`Scenario::expand`] can expand tokens and
    /// check the result again.
    pub(crate) source: Value,
}

/// The engine of a scenario.
#[derive(Debug, Clone, PartialEq)]
pub enum EngineSpec {
    /// The in-process scripted engine.
    Mock(MockEngineSpec),
    /// A line-protocol fake engine run as a child process.
    Line(LineEngineSpec),
}

/// The in-process scripted engine: it replays its scripts as token ids, one per step,
/// then the end-of-turn token; with several scripts the k-th generate call gets the k-th
/// and the last repeats.
///
/// Behavior reference: project-maya serve/server.py:199-240 at 7e68a30f.
#[derive(Debug, Clone, PartialEq)]
pub struct MockEngineSpec {
    /// The tokenizer it encodes its scripts with.
    pub tokenizer: TokenizerSpec,
    /// Its scripts, repeats expanded.
    pub script: Vec<String>,
    /// Its context size; 32768 when not given, as the donor's default.
    pub max_context: u64,
    /// Members merged over the engine's `info`.
    pub info: Map<String, Value>,
    /// A delay before each step, in milliseconds; 0 when not given.
    pub delay_ms: u64,
    /// The pacing rate in tokens per second, when given.
    pub tok_s: Option<f64>,
}

/// The default `max_context` of the scripted engine.
///
/// Behavior reference: project-maya serve/server.py:203 at 7e68a30f.
pub const MOCK_DEFAULT_MAX_CONTEXT: u64 = 32768;

/// Which line-protocol fake runs.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LineFake {
    /// The single-conversation GLM fake (`glm_dsa_fake_engine.py` in the donor).
    Glm,
    /// The several-conversation fake (`fake_multi_engine.py` in the donor).
    Multi,
}

/// A line-protocol fake engine.
#[derive(Debug, Clone, PartialEq)]
pub struct LineEngineSpec {
    /// Which fake.
    pub fake: LineFake,
    /// The server's tokenizer for this engine; always `bpe-bytes`, because the donor
    /// refuses to start a line engine whose tokenizer directory has no `vocab.json`
    /// (serve/server.py:7180-7181 at 7e68a30f).
    pub tokenizer: TokenizerSpec,
    /// Its command-line arguments.
    pub args: Vec<String>,
    /// Its environment, passed verbatim (naming.md rule 3), in the order written.
    pub env: Vec<(String, String)>,
}

/// How the server under test is started.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct ServerSpec {
    /// Extra command-line flags, in order.
    pub flags: Vec<String>,
    /// Extra environment, in the order written.
    pub env: Vec<(String, String)>,
    /// The run config written for the server.
    pub config: Map<String, Value>,
    /// Files written into the data directory before start, by relative path.
    pub data_dir: Vec<(String, DataFile)>,
}

/// A file written into the data directory.
#[derive(Debug, Clone, PartialEq)]
pub enum DataFile {
    /// Text written as is.
    Text(String),
    /// A JSON object or array, written as JSON.
    Json(Value),
}

/// One step: a request, a gate, a signal, or a request with a gate.
///
/// The runner executes the steps in order, with these semantics:
///
/// - Engine steps are counted per generate call of the engine, from 0: step `n` is the
///   point before that call yields its `n`-th token (step 0 is before the first). A
///   generate call blocks before step `n` when the scenario names `n` in any
///   `wait_for_engine_step` or `release_engine_step`, until a step releases `n`; once
///   released, gate `n` stays open for the rest of the run, for every call.
/// - Inside one step the order is: first `wait_for_engine_step` (wait until some generate
///   call is blocked at that gate), then the request is started (or the signal sent),
///   then `release_engine_step`.
/// - A request outside a concurrent group is sent and its response read to the end (or
///   to its disconnect) before the step's release and before the next step.
/// - The requests of a concurrent group are started in step order without waiting for
///   their responses; the group is joined (every response read to the end or to its
///   disconnect) at the first step after the group, or at the end of the steps. A step of
///   a group may be gate-only (no request), so a scenario can hold request A, send B and
///   release A within one group without a deadlock.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Step {
    /// The request sent.
    pub request: Option<Request>,
    /// When to drop the connection while reading the response.
    pub disconnect: Option<Disconnect>,
    /// Before anything else in this step, wait until a generate call is blocked at the
    /// gate before this engine step number.
    pub wait_for_engine_step: Option<u64>,
    /// After this step's request is started, open the gate before this engine step number.
    pub release_engine_step: Option<u64>,
    /// Steps with the same group run concurrently; a group is contiguous and is joined
    /// at the first step after it.
    pub concurrent_group: Option<String>,
    /// A signal sent to the server process.
    pub signal: Option<Signal>,
}

/// A request.
#[derive(Debug, Clone, PartialEq)]
pub enum Request {
    /// A request described field by field.
    Structured(StructuredRequest),
    /// A request sent as written (after token expansion), for malformed-input tests.
    Raw(String),
}

/// A request described field by field.
#[derive(Debug, Clone, PartialEq)]
pub struct StructuredRequest {
    /// The method, upper case.
    pub method: String,
    /// The request target, starting with `/` (or `*`).
    pub path: String,
    /// Headers in order, duplicates kept.
    pub headers: Vec<(String, String)>,
    /// The body.
    pub body: Body,
    /// The HTTP version of the request line; 1.1 when not given.
    pub http_version: HttpVersion,
}

/// A request body.
#[derive(Debug, Clone, PartialEq)]
pub enum Body {
    /// No body.
    None,
    /// A JSON value, serialized by the runner.
    Json(Value),
    /// Text sent as is.
    Text(String),
    /// A file next to the scenario file, by relative path.
    File(String),
}

/// The HTTP version of a request line.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HttpVersion {
    /// `HTTP/1.0`.
    V1_0,
    /// `HTTP/1.1`.
    V1_1,
}

/// When the client drops the connection.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Disconnect {
    /// After this many stream events have been read.
    AfterEvents(u64),
    /// After this many response bytes have been read.
    AfterBytes(u64),
}

/// A signal the harness sends to the server process.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Signal {
    /// `SIGTERM`.
    Term,
    /// `SIGHUP`.
    Hup,
    /// `SIGINT`.
    Int,
}

impl Signal {
    /// The signal's name as a scenario writes it.
    pub fn name(self) -> &'static str {
        match self {
            Signal::Term => "SIGTERM",
            Signal::Hup => "SIGHUP",
            Signal::Int => "SIGINT",
        }
    }
}

/// What a scenario records.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct Observe {
    /// Status, headers and body of every response.
    pub http: bool,
    /// Every input the engine sees.
    pub engine_tape: bool,
    /// Files under the data directory matching these globs.
    pub files: Vec<String>,
    /// Contracted log lines, by id.
    pub log: Vec<String>,
    /// The server's exit status.
    pub exit: bool,
}

/// Checks a parsed document and builds the scenario. `bind` is the only bind address
/// the document may name: [`LOOPBACK_TOKEN`] as written, or the harness's loopback
/// address once [`Scenario::expand`] has filled the token.
pub(crate) fn scenario_from_value(value: &Value, bind: &str) -> Result<Scenario> {
    let obj = Obj::of(value, "")?;
    obj.allow_only(schema::SCENARIO.properties)?;

    let (v, p) = obj.required("id")?;
    let id = id_string(v, &p)?.to_string();

    let description = optional_string(&obj, "description", MAX_DESCRIPTION_CHARS)?;

    let mut donor = Vec::new();
    if let Some((v, p)) = obj.get("donor") {
        for (i, item) in json::nonempty_array(v, &p, MAX_DONOR_ENTRIES)?
            .iter()
            .enumerate()
        {
            let ip = json::index(&p, i);
            let s = json::string(item, &ip, MAX_DONOR_CHARS)?;
            if !is_donor_test_id(s) {
                return Err(ScenarioError::invalid(
                    ip,
                    "must name a donor test as serve/test_<name>.py::Class::method or serve/test_<name>.py::function",
                ));
            }
            if donor.iter().any(|d| d == s) {
                return Err(ScenarioError::invalid(ip, "listed twice"));
            }
            donor.push(s.to_string());
        }
    }

    let notes = optional_string(&obj, "notes", MAX_NOTES_CHARS)?;

    let (v, p) = obj.required("engine")?;
    let engine = engine(v, &p)?;

    let (v, p) = obj.required("template")?;
    let template = template_ref(v, &p)?;

    let server = match obj.get("server") {
        Some((v, p)) => server(v, &p, &engine, bind)?,
        None => ServerSpec::default(),
    };

    let (v, p) = obj.required("steps")?;
    let steps = steps(v, &p)?;

    let (v, p) = obj.required("observe")?;
    let observe = observe(v, &p)?;

    subst::check_tokens(value, "")?;

    Ok(Scenario {
        id,
        description,
        donor,
        notes,
        engine,
        template,
        server,
        steps,
        observe,
        source: value.clone(),
    })
}

fn optional_string(obj: &Obj<'_>, key: &str, max: usize) -> Result<Option<String>> {
    match obj.get(key) {
        Some((v, p)) => Ok(Some(json::nonempty_string(v, &p, max)?.to_string())),
        None => Ok(None),
    }
}

fn id_string<'a>(v: &'a Value, p: &str) -> Result<&'a str> {
    let s = json::nonempty_string(v, p, MAX_ID_CHARS)?;
    let mut bytes = s.bytes();
    let first_ok = bytes
        .next()
        .is_some_and(|b| b.is_ascii_lowercase() || b.is_ascii_digit());
    let rest_ok = s
        .bytes()
        .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-');
    if !first_ok || !rest_ok || s.ends_with('-') {
        return Err(ScenarioError::invalid(
            p,
            "must be lower-case letters, digits and hyphens, starting with a letter or digit and not ending with a hyphen",
        ));
    }
    Ok(s)
}

/// `serve/test_<name>.py::Class::method` or `serve/test_<name>.py::function`.
pub(crate) fn is_donor_test_id(s: &str) -> bool {
    let mut parts = s.split("::");
    let Some(file) = parts.next() else {
        return false;
    };
    let file_ok = file
        .strip_prefix("serve/test_")
        .and_then(|rest| rest.strip_suffix(".py"))
        .is_some_and(|stem| {
            !stem.is_empty()
                && stem
                    .bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
        });
    let names: Vec<&str> = parts.collect();
    file_ok && (1..=2).contains(&names.len()) && names.iter().all(|n| is_identifier(n))
}

fn is_identifier(s: &str) -> bool {
    let mut bytes = s.bytes();
    bytes
        .next()
        .is_some_and(|b| b.is_ascii_alphabetic() || b == b'_')
        && bytes.all(|b| b.is_ascii_alphanumeric() || b == b'_')
}

fn engine(v: &Value, p: &str) -> Result<EngineSpec> {
    let obj = Obj::of(v, p)?;
    let (kv, kp) = obj.required("kind")?;
    match json::string(kv, &kp, 16)? {
        "mock" => mock_engine(&obj).map(EngineSpec::Mock),
        "line" => line_engine(&obj).map(EngineSpec::Line),
        _ => Err(ScenarioError::invalid(kp, "must be \"mock\" or \"line\"")),
    }
}

fn mock_engine(obj: &Obj<'_>) -> Result<MockEngineSpec> {
    obj.allow_only(schema::ENGINE_MOCK.properties)?;
    let (v, p) = obj.required("tokenizer")?;
    let tokenizer = tokenizer(v, &p)?;

    let (v, p) = obj.required("script")?;
    let items = json::nonempty_array(v, &p, MAX_SCRIPT_ENTRIES)?;
    let mut script = Vec::with_capacity(items.len());
    let mut total = 0usize;
    for (i, item) in items.iter().enumerate() {
        let ip = json::index(&p, i);
        let text = script_entry(item, &ip)?;
        total = total.saturating_add(text.len());
        if total > MAX_SCRIPT_BYTES {
            return Err(ScenarioError::invalid(
                ip,
                format!("the scripts together exceed {MAX_SCRIPT_BYTES} bytes"),
            ));
        }
        script.push(text);
    }

    let max_context = match obj.get("max_context") {
        Some((v, p)) => json::uint(v, &p, 1, MAX_CONTEXT)?,
        None => MOCK_DEFAULT_MAX_CONTEXT,
    };
    let info = match obj.get("info") {
        Some((v, p)) => match v {
            Value::Object(map) => map.clone(),
            other => return Err(json::type_error(&p, "object", other)),
        },
        None => Map::new(),
    };
    let delay_ms = match obj.get("delay_ms") {
        Some((v, p)) => json::uint(v, &p, 0, MAX_DELAY_MS)?,
        None => 0,
    };
    let tok_s = match obj.get("tok_s") {
        Some((v, p)) => Some(json::positive_number(v, &p, MAX_TOK_S)?),
        None => None,
    };
    Ok(MockEngineSpec {
        tokenizer,
        script,
        max_context,
        info,
        delay_ms,
        tok_s,
    })
}

fn script_entry(v: &Value, p: &str) -> Result<String> {
    match v {
        Value::String(s) => {
            if s.len() > MAX_SCRIPT_BYTES {
                return Err(ScenarioError::invalid(
                    p,
                    format!("longer than {MAX_SCRIPT_BYTES} bytes"),
                ));
            }
            Ok(s.clone())
        }
        Value::Object(_) => {
            let obj = Obj::of(v, p)?;
            obj.allow_only(schema::SCRIPT_REPEAT.properties)?;
            let (rv, rp) = obj.required("repeat")?;
            let unit = json::nonempty_string(rv, &rp, MAX_SCRIPT_BYTES)?;
            let (tv, tp) = obj.required("times")?;
            let times = json::uint(tv, &tp, 1, MAX_SCRIPT_BYTES as u64)?;
            let len = usize::try_from(times)
                .ok()
                .and_then(|t| t.checked_mul(unit.len()))
                .filter(|n| *n <= MAX_SCRIPT_BYTES);
            match len {
                Some(_) => Ok(unit.repeat(usize::try_from(times).unwrap_or(0))),
                None => Err(ScenarioError::invalid(
                    p,
                    format!("the repeated text exceeds {MAX_SCRIPT_BYTES} bytes"),
                )),
            }
        }
        other => Err(json::type_error(p, "string or object", other)),
    }
}

fn tokenizer(v: &Value, p: &str) -> Result<TokenizerSpec> {
    let obj = Obj::of(v, p)?;
    let (kv, kp) = obj.required("kind")?;
    match json::string(kv, &kp, 16)? {
        "byte" => {
            obj.allow_only(schema::TOKENIZER_BYTE.properties)?;
            let mut extra: Vec<String> = Vec::new();
            if let Some((v, p)) = obj.get("extra_specials") {
                for (i, item) in json::array(v, &p, MAX_SPECIALS)?.iter().enumerate() {
                    let ip = json::index(&p, i);
                    let s = json::nonempty_string(item, &ip, MAX_SPECIAL_CHARS)?;
                    if BYTE_SPECIALS.contains(&s) || extra.iter().any(|e| e == s) {
                        return Err(ScenarioError::invalid(ip, "a special listed twice"));
                    }
                    extra.push(s.to_string());
                }
            }
            Ok(TokenizerSpec::Byte {
                extra_specials: extra,
            })
        }
        "bpe-bytes" => {
            obj.allow_only(schema::TOKENIZER_BPE_BYTES.properties)?;
            let mut added: Vec<(String, u32)> = Vec::new();
            if let Some((v, p)) = obj.get("added") {
                let map = json::object_limited(v, &p, MAX_SPECIALS)?;
                let byte_chars: Vec<char> =
                    byte_level_chars().into_iter().map(|(c, _)| c).collect();
                for (piece, idv) in map {
                    let ip = json::child(&p, piece);
                    if piece.is_empty() || piece.chars().count() > MAX_SPECIAL_CHARS {
                        return Err(ScenarioError::invalid(
                            ip,
                            format!("an added token must be 1 to {MAX_SPECIAL_CHARS} characters"),
                        ));
                    }
                    let mut chars = piece.chars();
                    if let (Some(c), None) = (chars.next(), chars.next()) {
                        if byte_chars.contains(&c) {
                            return Err(ScenarioError::invalid(
                                ip,
                                "an added token may not be one of the 256 byte characters",
                            ));
                        }
                    }
                    let id = json::uint(idv, &ip, u64::from(FIRST_SPECIAL_ID), MAX_TOKEN_ID)?;
                    let id = u32::try_from(id).unwrap_or(u32::MAX);
                    if added.iter().any(|(_, other)| *other == id) {
                        return Err(ScenarioError::invalid(ip, "this id is given twice"));
                    }
                    added.push((piece.clone(), id));
                }
            }
            Ok(TokenizerSpec::BpeBytes { added })
        }
        _ => Err(ScenarioError::invalid(
            kp,
            "must be \"byte\" or \"bpe-bytes\"",
        )),
    }
}

fn line_engine(obj: &Obj<'_>) -> Result<LineEngineSpec> {
    obj.allow_only(schema::ENGINE_LINE.properties)?;
    let (v, p) = obj.required("fake")?;
    let fake = match json::string(v, &p, 16)? {
        "glm" => LineFake::Glm,
        "multi" => LineFake::Multi,
        _ => return Err(ScenarioError::invalid(p, "must be \"glm\" or \"multi\"")),
    };
    let (v, p) = obj.required("tokenizer")?;
    let tokenizer = tokenizer(v, &p)?;
    if matches!(tokenizer, TokenizerSpec::Byte { .. }) {
        return Err(ScenarioError::invalid(
            p,
            "a line engine needs a bpe-bytes tokenizer: the server refuses a line engine whose tokenizer has no vocab.json",
        ));
    }
    let args = match obj.get("args") {
        Some((v, p)) => string_list(v, &p, MAX_ARGS, MAX_ARG_CHARS)?,
        None => Vec::new(),
    };
    let env = match obj.get("env") {
        Some((v, p)) => env_map(v, &p)?,
        None => Vec::new(),
    };
    Ok(LineEngineSpec {
        fake,
        tokenizer,
        args,
        env,
    })
}

fn string_list(v: &Value, p: &str, max_entries: usize, max_chars: usize) -> Result<Vec<String>> {
    json::array(v, p, max_entries)?
        .iter()
        .enumerate()
        .map(|(i, item)| {
            let ip = json::index(p, i);
            let s = json::string(item, &ip, max_chars)?;
            if s.contains('\0') {
                return Err(ScenarioError::invalid(ip, "must not contain NUL"));
            }
            Ok(s.to_string())
        })
        .collect()
}

fn env_map(v: &Value, p: &str) -> Result<Vec<(String, String)>> {
    let map = json::object_limited(v, p, MAX_ENV)?;
    let mut out = Vec::with_capacity(map.len());
    for (name, value) in map {
        let ip = json::child(p, name);
        let name_ok = !name.is_empty()
            && name.len() <= MAX_ENV_NAME_CHARS
            && name
                .bytes()
                .next()
                .is_some_and(|b| b.is_ascii_uppercase() || b == b'_')
            && name
                .bytes()
                .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit() || b == b'_');
        if !name_ok {
            return Err(ScenarioError::invalid(
                ip,
                format!("an environment name must match [A-Z_][A-Z0-9_]* and be at most {MAX_ENV_NAME_CHARS} characters"),
            ));
        }
        if is_reserved_env(name) {
            return Err(ScenarioError::invalid(
                ip,
                "set by the harness: PATH, HOME, TZ, LC_ALL, LANG, TMPDIR, PULSAR_CONSOLE_VENDOR_DIR, FAKE_ENGINE_GATE and names starting with XDG_, LD_, DYLD_ or PYTHON are reserved",
            ));
        }
        let s = json::string(value, &ip, MAX_ENV_VALUE_CHARS)?;
        if s.contains('\0') {
            return Err(ScenarioError::invalid(ip, "must not contain NUL"));
        }
        out.push((name.clone(), s.to_string()));
    }
    Ok(out)
}

fn template_ref(v: &Value, p: &str) -> Result<TemplateRef> {
    let s = json::nonempty_string(v, p, MAX_TEMPLATE_REF_CHARS)?;
    if let Some(rel) = s.strip_prefix("vendor:") {
        if !is_safe_relative_path(rel, false) || !rel.ends_with(".jinja") {
            return Err(ScenarioError::invalid(
                p,
                "a vendor template is vendor:<relative path ending in .jinja>, with segments of [A-Za-z0-9._-] and no . or .. segment",
            ));
        }
        return Ok(TemplateRef::Vendor(rel.to_string()));
    }
    let ok = s
        .bytes()
        .next()
        .is_some_and(|b| b.is_ascii_lowercase() || b.is_ascii_digit())
        && s.bytes().all(|b| {
            b.is_ascii_lowercase() || b.is_ascii_digit() || matches!(b, b'-' | b'_' | b'.')
        })
        && !s.contains("..")
        && !s.ends_with(".jinja");
    if !ok {
        return Err(ScenarioError::invalid(
            p,
            "a project template is a name of [a-z0-9._-] starting with a letter or digit, without .. or the .jinja suffix; a vendor template starts with vendor:",
        ));
    }
    Ok(TemplateRef::Project(s.to_string()))
}

/// A relative path: segments of `[A-Za-z0-9._-]` (and `*`, `?` and a whole `**` segment
/// when `glob`), separated by `/`, none empty, `.` or `..`, no leading `/`.
pub(crate) fn is_safe_relative_path(s: &str, glob: bool) -> bool {
    if s.is_empty() || s.chars().count() > MAX_PATH_CHARS {
        return false;
    }
    s.split('/').all(|seg| {
        !seg.is_empty()
            && seg != "."
            && seg != ".."
            && ((glob && seg == "**")
                || (seg.bytes().all(|b| {
                    b.is_ascii_alphanumeric()
                        || matches!(b, b'.' | b'_' | b'-')
                        || (glob && matches!(b, b'*' | b'?'))
                }) && !seg.contains("**")))
    })
}

fn server(v: &Value, p: &str, engine: &EngineSpec, bind: &str) -> Result<ServerSpec> {
    let obj = Obj::of(v, p)?;
    obj.allow_only(schema::SERVER.properties)?;
    let mut spec = ServerSpec::default();
    if let Some((v, p)) = obj.get("flags") {
        spec.flags = string_list(v, &p, MAX_ARGS, MAX_ARG_CHARS)?;
        for (i, flag) in spec.flags.iter().enumerate() {
            let (name, inline) = match flag.split_once('=') {
                Some((name, value)) => (name, Some(value)),
                None => (flag.as_str(), None),
            };
            if let Some(full) = HARNESS_FLAGS
                .iter()
                .find(|full| is_abbreviation_of(name, full))
            {
                return Err(ScenarioError::invalid(
                    json::index(&p, i),
                    format!("{name} means {full}, which the harness sets from the scenario"),
                ));
            }
            if is_abbreviation_of(name, HOST_FLAG) {
                let value = inline.or_else(|| spec.flags.get(i + 1).map(String::as_str));
                if value != Some(bind) {
                    return Err(ScenarioError::invalid(
                        json::index(&p, i),
                        format!("the harness binds loopback: {name} may only take the value {LOOPBACK_TOKEN}"),
                    ));
                }
            }
        }
    }
    if let Some((v, p)) = obj.get("env") {
        spec.env = env_map(v, &p)?;
    }
    if let Some((v, p)) = obj.get("config") {
        let map = match v {
            Value::Object(map) => map,
            other => return Err(json::type_error(&p, "object", other)),
        };
        if let Some(bind_value) = map.get(HOST_CONFIG_KEY) {
            if bind_value.as_str() != Some(bind) {
                return Err(ScenarioError::invalid(
                    json::child(&p, HOST_CONFIG_KEY),
                    format!("the harness binds loopback: the run config's bind address may only be {LOOPBACK_TOKEN}"),
                ));
            }
        }
        if matches!(engine, EngineSpec::Line(_)) {
            if let Some(key) = map
                .keys()
                .find(|k| HARNESS_CONFIG_KEYS.contains(&k.as_str()))
            {
                return Err(ScenarioError::invalid(
                    json::child(&p, key),
                    "set by the harness from the line engine's spec",
                ));
            }
        }
        spec.config = map.clone();
    }
    if let Some((v, p)) = obj.get("data_dir") {
        let map = json::object_limited(v, &p, MAX_DATA_FILES)?;
        for (path, content) in map {
            let ip = json::child(&p, path);
            if !is_safe_relative_path(path, false) {
                return Err(ScenarioError::invalid(
                    ip,
                    "a data_dir path is relative, with segments of [A-Za-z0-9._-] and no . or .. segment",
                ));
            }
            let file = match content {
                Value::String(s) => DataFile::Text(s.clone()),
                Value::Object(_) | Value::Array(_) => DataFile::Json(content.clone()),
                other => return Err(json::type_error(&ip, "string, object or array", other)),
            };
            spec.data_dir.push((path.clone(), file));
        }
    }
    Ok(spec)
}

fn steps(v: &Value, p: &str) -> Result<Vec<Step>> {
    let items = json::nonempty_array(v, p, MAX_STEPS)?;
    let mut out: Vec<Step> = Vec::with_capacity(items.len());
    let mut closed_groups: Vec<String> = Vec::new();
    for (i, item) in items.iter().enumerate() {
        let ip = json::index(p, i);
        let step = step(item, &ip)?;
        let previous = out.last().and_then(|s| s.concurrent_group.clone());
        if previous.is_some() && previous != step.concurrent_group {
            if let Some(g) = previous {
                closed_groups.push(g);
            }
        }
        if let Some(group) = &step.concurrent_group {
            if closed_groups.contains(group) {
                return Err(ScenarioError::invalid(
                    json::child(&ip, "concurrent_group"),
                    format!("the steps of group {group:?} must be contiguous"),
                ));
            }
        }
        out.push(step);
    }
    Ok(out)
}

fn step(v: &Value, p: &str) -> Result<Step> {
    let obj = Obj::of(v, p)?;
    obj.allow_only(schema::STEP.properties)?;
    obj.exclusive("disconnect_after_events", "disconnect_after_bytes")?;
    obj.exclusive("request", "signal")?;
    let mut step = Step::default();
    if let Some((v, p)) = obj.get("request") {
        step.request = Some(request(v, &p)?);
    }
    if let Some((v, p)) = obj.get("disconnect_after_events") {
        step.disconnect = Some(Disconnect::AfterEvents(json::uint(v, &p, 1, MAX_EVENTS)?));
    }
    if let Some((v, p)) = obj.get("disconnect_after_bytes") {
        step.disconnect = Some(Disconnect::AfterBytes(json::uint(v, &p, 1, MAX_BYTES)?));
    }
    if let Some((v, p)) = obj.get("wait_for_engine_step") {
        step.wait_for_engine_step = Some(json::uint(v, &p, 0, MAX_ENGINE_STEP)?);
    }
    if let Some((v, p)) = obj.get("release_engine_step") {
        step.release_engine_step = Some(json::uint(v, &p, 0, MAX_ENGINE_STEP)?);
    }
    if let Some((v, p)) = obj.get("concurrent_group") {
        step.concurrent_group = Some(name_string(v, &p)?.to_string());
    }
    if let Some((v, p)) = obj.get("signal") {
        step.signal = Some(match json::string(v, &p, 16)? {
            "SIGTERM" => Signal::Term,
            "SIGHUP" => Signal::Hup,
            "SIGINT" => Signal::Int,
            _ => {
                return Err(ScenarioError::invalid(
                    p,
                    "must be \"SIGTERM\", \"SIGHUP\" or \"SIGINT\"",
                ))
            }
        });
    }
    if step.request.is_none() {
        if step.disconnect.is_some() {
            return Err(ScenarioError::invalid(
                p,
                "a disconnect needs a request in the same step",
            ));
        }
        if step.concurrent_group.is_some()
            && step.wait_for_engine_step.is_none()
            && step.release_engine_step.is_none()
        {
            return Err(ScenarioError::invalid(
                p,
                "a concurrent_group step needs a request or an engine gate",
            ));
        }
        if step.wait_for_engine_step.is_none()
            && step.release_engine_step.is_none()
            && step.signal.is_none()
        {
            return Err(ScenarioError::invalid(
                p,
                "a step needs a request, an engine gate or a signal",
            ));
        }
    }
    Ok(step)
}

fn name_string<'a>(v: &'a Value, p: &str) -> Result<&'a str> {
    let s = json::nonempty_string(v, p, MAX_NAME_CHARS)?;
    if !s
        .bytes()
        .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || matches!(b, b'-' | b'_' | b'.'))
    {
        return Err(ScenarioError::invalid(p, "must be made of [a-z0-9._-]"));
    }
    Ok(s)
}

fn request(v: &Value, p: &str) -> Result<Request> {
    let obj = Obj::of(v, p)?;
    if obj.map.contains_key("raw") {
        obj.allow_only(schema::REQUEST_RAW.properties)?;
        let (rv, rp) = obj.required("raw")?;
        let raw = json::nonempty_string(rv, &rp, MAX_RAW_CHARS)?;
        return Ok(Request::Raw(raw.to_string()));
    }
    obj.allow_only(schema::REQUEST.properties)?;
    obj.exclusive("body", "body_text")?;
    obj.exclusive("body", "body_file")?;
    obj.exclusive("body_text", "body_file")?;

    let (mv, mp) = obj.required("method")?;
    let method = json::nonempty_string(mv, &mp, MAX_METHOD_CHARS)?;
    if !method.bytes().all(|b| b.is_ascii_uppercase()) {
        return Err(ScenarioError::invalid(
            mp,
            "a method is upper-case letters; use a raw request for anything else",
        ));
    }

    let (tv, tp) = obj.required("path")?;
    let path = json::nonempty_string(tv, &tp, MAX_REQUEST_PATH_CHARS)?;
    let path_ok = (path.starts_with('/') || path == "*")
        && !path.chars().any(|c| c.is_whitespace() || c.is_control());
    if !path_ok {
        return Err(ScenarioError::invalid(
            tp,
            "a path starts with / (or is *) and holds no whitespace or control character; use a raw request for anything else",
        ));
    }

    let mut headers = Vec::new();
    if let Some((hv, hp)) = obj.get("headers") {
        for (i, pair) in json::array(hv, &hp, MAX_HEADERS)?.iter().enumerate() {
            let ip = json::index(&hp, i);
            let items = json::array(pair, &ip, 2)?;
            let (Some(name), Some(value), 2) = (items.first(), items.get(1), items.len()) else {
                return Err(ScenarioError::invalid(
                    ip,
                    "a header is a [name, value] pair",
                ));
            };
            let np = json::index(&ip, 0);
            let name = json::nonempty_string(name, &np, MAX_HEADER_NAME_CHARS)?;
            if !name.bytes().all(is_tchar) {
                return Err(ScenarioError::invalid(np, "a header name is an HTTP token"));
            }
            let vp = json::index(&ip, 1);
            let value = json::string(value, &vp, MAX_HEADER_VALUE_CHARS)?;
            if value.contains(['\r', '\n', '\0']) {
                return Err(ScenarioError::invalid(
                    vp,
                    "a header value holds no CR, LF or NUL; use a raw request for that",
                ));
            }
            headers.push((name.to_string(), value.to_string()));
        }
    }

    let body = if let Some((bv, _)) = obj.get("body") {
        Body::Json(bv.clone())
    } else if let Some((bv, bp)) = obj.get("body_text") {
        Body::Text(json::string(bv, &bp, MAX_RAW_CHARS)?.to_string())
    } else if let Some((bv, bp)) = obj.get("body_file") {
        let rel = json::nonempty_string(bv, &bp, MAX_PATH_CHARS)?;
        if !is_safe_relative_path(rel, false) {
            return Err(ScenarioError::invalid(
                bp,
                "a body file is a relative path next to the scenario, with segments of [A-Za-z0-9._-] and no . or .. segment",
            ));
        }
        Body::File(rel.to_string())
    } else {
        Body::None
    };

    let http_version = match obj.get("http_version") {
        Some((v, p)) => match json::string(v, &p, 8)? {
            "1.0" => HttpVersion::V1_0,
            "1.1" => HttpVersion::V1_1,
            _ => return Err(ScenarioError::invalid(p, "must be \"1.0\" or \"1.1\"")),
        },
        None => HttpVersion::V1_1,
    };

    Ok(Request::Structured(StructuredRequest {
        method: method.to_string(),
        path: path.to_string(),
        headers,
        body,
        http_version,
    }))
}

/// An RFC 9110 token character.
fn is_tchar(b: u8) -> bool {
    b.is_ascii_alphanumeric()
        || matches!(
            b,
            b'!' | b'#'
                | b'$'
                | b'%'
                | b'&'
                | b'\''
                | b'*'
                | b'+'
                | b'-'
                | b'.'
                | b'^'
                | b'_'
                | b'`'
                | b'|'
                | b'~'
        )
}

fn observe(v: &Value, p: &str) -> Result<Observe> {
    let obj = Obj::of(v, p)?;
    obj.allow_only(schema::OBSERVE.properties)?;
    let mut o = Observe::default();
    if let Some((v, p)) = obj.get("http") {
        o.http = json::boolean(v, &p)?;
    }
    if let Some((v, p)) = obj.get("engine_tape") {
        o.engine_tape = json::boolean(v, &p)?;
    }
    if let Some((v, p)) = obj.get("files") {
        for (i, item) in json::nonempty_array(v, &p, MAX_OBSERVED)?
            .iter()
            .enumerate()
        {
            let ip = json::index(&p, i);
            let g = json::nonempty_string(item, &ip, MAX_PATH_CHARS)?;
            if !is_safe_relative_path(g, true) {
                return Err(ScenarioError::invalid(
                    ip,
                    "a file glob is relative to the data directory: segments of [A-Za-z0-9._-*?] or a whole ** segment, no . or .. segment",
                ));
            }
            o.files.push(g.to_string());
        }
    }
    if let Some((v, p)) = obj.get("log") {
        for (i, item) in json::nonempty_array(v, &p, MAX_OBSERVED)?
            .iter()
            .enumerate()
        {
            let ip = json::index(&p, i);
            o.log.push(name_string(item, &ip)?.to_string());
        }
    }
    if let Some((v, p)) = obj.get("exit") {
        o.exit = json::boolean(v, &p)?;
    }
    if !(o.http || o.engine_tape || o.exit || !o.files.is_empty() || !o.log.is_empty()) {
        return Err(ScenarioError::new(
            p,
            ErrorKind::InvalidValue {
                reason: "observe at least one of http, engine_tape, files, log or exit".into(),
            },
        ));
    }
    Ok(o)
}
