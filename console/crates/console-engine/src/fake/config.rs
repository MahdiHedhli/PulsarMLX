//! The scripted engine's settings: the [`FakeScript`] builder, its limits, and the two
//! test-harness environment settings of the donor's mock engine under their
//! `PULSAR_CONSOLE_` names (decision B2; contracts/naming.md).

use std::fmt;
use std::sync::Arc;
use std::time::Duration;

use super::clock::{FakeClock, SystemClock};
use super::factory::FakeFactory;

/// The most scripts one engine rotates through.
pub const MAX_SCRIPTS: usize = 256;

/// The most token ids one script holds.
pub const MAX_SCRIPT_TOKENS: usize = 1 << 20;

/// The donor mock engine's context when none is given.
///
/// Behavior reference: project-maya serve/server.py:203 at 7e68a30f.
pub const DEFAULT_MAX_CONTEXT: u32 = 32_768;

/// How long a context reload of the scripted engine takes when
/// [`RELOAD_DELAY_ENV`] is not set: 2 seconds.
///
/// Behavior reference: project-maya serve/server.py:2771 at 7e68a30f.
pub const DEFAULT_RELOAD_DELAY: Duration = Duration::from_secs(2);

/// The donor's `MAYA_MOCK_RELOAD_S`, renamed mechanically (contracts/naming.md). The
/// legacy name is not read (BRAND-1).
pub const RELOAD_DELAY_ENV: &str = "PULSAR_CONSOLE_MOCK_RELOAD_S";

/// The donor's `MAYA_MOCK_TOK_S`, renamed mechanically (contracts/naming.md). The legacy
/// name is not read (BRAND-1).
pub const TOK_S_ENV: &str = "PULSAR_CONSOLE_MOCK_TOK_S";

/// A setting of the scripted engine that cannot be used.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FakeConfigError {
    /// No script was given.
    NoScript,
    /// More than [`MAX_SCRIPTS`] scripts.
    TooManyScripts {
        /// How many were given.
        count: usize,
    },
    /// A script longer than [`MAX_SCRIPT_TOKENS`].
    ScriptTooLong {
        /// Its 0-based place in the rotation.
        index: usize,
        /// Its length.
        len: usize,
    },
    /// A value Python's `float()` does not read; the text is Python's `ValueError`.
    NotANumber {
        /// The setting.
        name: &'static str,
        /// The value as given.
        value: String,
    },
    /// A number Python's `time.sleep` refuses: not a number, negative, or beyond its
    /// range (about 292 years, the range of CPython's nanosecond `_PyTime_t`).
    BadDuration {
        /// The setting.
        name: &'static str,
        /// The value as given.
        value: String,
        /// The text of the error `time.sleep` raises for it.
        reason: &'static str,
    },
}

impl fmt::Display for FakeConfigError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            FakeConfigError::NoScript => f.write_str("the scripted engine needs a script"),
            FakeConfigError::TooManyScripts { count } => write!(
                f,
                "the scripted engine takes at most {MAX_SCRIPTS} scripts ({count} given)"
            ),
            FakeConfigError::ScriptTooLong { index, len } => write!(
                f,
                "script {index} has {len} tokens; at most {MAX_SCRIPT_TOKENS} are allowed"
            ),
            FakeConfigError::NotANumber { name, value } => write!(
                f,
                "{name}: could not convert string to float: '{}'",
                value.escape_debug()
            ),
            FakeConfigError::BadDuration { name, reason, .. } => write!(f, "{name}: {reason}"),
        }
    }
}

impl std::error::Error for FakeConfigError {}

/// Removes single underscores that stand between two ASCII digits, as Python's `float()`
/// allows; `None` for any other underscore or for non-ASCII text.
fn strip_digit_underscores(s: &str) -> Option<String> {
    if !s.is_ascii() {
        return None;
    }
    let bytes = s.as_bytes();
    let mut out = String::with_capacity(s.len());
    for (i, &b) in bytes.iter().enumerate() {
        if b == b'_' {
            let before = i.checked_sub(1).and_then(|j| bytes.get(j));
            match (before, bytes.get(i + 1)) {
                (Some(x), Some(y)) if x.is_ascii_digit() && y.is_ascii_digit() => continue,
                _ => return None,
            }
        }
        out.push(char::from(b));
    }
    Some(out)
}

/// Python's `float()` on a setting's text: surrounding whitespace ignored, an optional
/// sign, decimal or exponent forms with single underscores between digits, and `inf`,
/// `infinity` and `nan` in any case. Non-ASCII digits, which Python also reads, are not
/// read here.
fn py_float(s: &str) -> Option<f64> {
    strip_digit_underscores(s.trim())?.parse::<f64>().ok()
}

/// The bound, in nanoseconds, of CPython's `time.sleep` timeout: a signed 64-bit count
/// of nanoseconds (`_PyTime_t`), 2^63, about 292 years.
const PY_TIME_LIMIT_NS: f64 = 9_223_372_036_854_775_808.0;

/// Python's `time.sleep(s)` on a float: the sleep, or the text of the error it raises
/// (as CPython 3.10 to 3.12 word it; the donor needs Python 3.10 or newer). A NaN is a
/// `ValueError`, a value whose nanoseconds fall outside `_PyTime_t` an `OverflowError`
/// (whatever its sign), and a negative value a `ValueError`; -0.0 sleeps for nothing.
/// No sleep beyond about 292 years is ever returned, so no sleep is unbounded.
pub(crate) fn py_sleep(s: f64) -> Result<Duration, &'static str> {
    if s.is_nan() {
        return Err("Invalid value NaN (not a number)");
    }
    let ns = s * 1e9;
    if !(-PY_TIME_LIMIT_NS..PY_TIME_LIMIT_NS).contains(&ns) {
        return Err("timestamp too large to convert to C _PyTime_t");
    }
    if s < 0.0 {
        return Err("sleep length must be non-negative");
    }
    if s == 0.0 {
        return Ok(Duration::ZERO);
    }
    // Finite, positive and within about 292 years: a `Duration` holds it.
    Duration::try_from_secs_f64(s).map_err(|_| "timestamp too large to convert to C _PyTime_t")
}

/// The context reload delay from the value of [`RELOAD_DELAY_ENV`]: unset means
/// [`DEFAULT_RELOAD_DELAY`], as `float(os.environ.get("MAYA_MOCK_RELOAD_S", "2"))` reads
/// it, and the value is then slept as `time.sleep` would. A value `float()` refuses is
/// [`FakeConfigError::NotANumber`]; one `time.sleep` refuses is
/// [`FakeConfigError::BadDuration`] with its text. The scripted engine reads the value at
/// each context reload, not when it is built, so a bad value fails only that reload, as
/// it does in the donor.
///
/// Behavior reference: project-maya serve/server.py:2765-2772 at 7e68a30f.
pub fn reload_delay_from(value: Option<&str>) -> Result<Duration, FakeConfigError> {
    let Some(v) = value else {
        return Ok(DEFAULT_RELOAD_DELAY);
    };
    let x = py_float(v).ok_or_else(|| FakeConfigError::NotANumber {
        name: RELOAD_DELAY_ENV,
        value: v.to_owned(),
    })?;
    py_sleep(x).map_err(|reason| FakeConfigError::BadDuration {
        name: RELOAD_DELAY_ENV,
        value: v.to_owned(),
        reason,
    })
}

/// The pacing speed from the value of [`TOK_S_ENV`], as
/// `float(os.environ.get("MAYA_MOCK_TOK_S") or 0) or None` reads it at start: unset, empty
/// or zero means no pacing (`None`). A value `float()` refuses is an error, as in the
/// donor, where the server then does not start. Any other number is kept, as the donor
/// keeps it: a speed whose sleep `time.sleep` refuses (negative, NaN, or so small that the
/// sleep passes about 292 years) fails each paced generation at its first token, with
/// the text of `time.sleep`'s error.
///
/// Behavior reference: project-maya serve/server.py:7287-7290, 230-231 at 7e68a30f.
pub fn tok_s_from(value: Option<&str>) -> Result<Option<f64>, FakeConfigError> {
    let v = match value {
        None => return Ok(None),
        Some("") => return Ok(None),
        Some(v) => v,
    };
    let x = py_float(v).ok_or_else(|| FakeConfigError::NotANumber {
        name: TOK_S_ENV,
        value: v.to_owned(),
    })?;
    Ok(no_pacing_at_zero(x))
}

/// `x or None`: 0 (and -0.0) is no pacing.
fn no_pacing_at_zero(x: f64) -> Option<f64> {
    if x == 0.0 {
        None
    } else {
        Some(x)
    }
}

/// How long a context reload takes: a fixed time, or the text of [`RELOAD_DELAY_ENV`],
/// read at each reload.
#[derive(Debug, Clone, PartialEq)]
pub(crate) enum ReloadDelay {
    Fixed(Duration),
    Text(String),
}

impl ReloadDelay {
    /// The sleep of one reload, or why the reload fails.
    pub(crate) fn resolve(&self) -> Result<Duration, FakeConfigError> {
        match self {
            ReloadDelay::Fixed(d) => Ok(*d),
            ReloadDelay::Text(t) => reload_delay_from(Some(t)),
        }
    }
}

/// The settings of a scripted engine, shared by every instance a factory starts.
#[derive(Debug, Clone)]
pub(crate) struct FakeConfig {
    pub(crate) scripts: Vec<Arc<[u32]>>,
    pub(crate) max_context: u32,
    pub(crate) delay: Duration,
    pub(crate) tok_s: Option<f64>,
    pub(crate) reload_delay: ReloadDelay,
    pub(crate) clock: Arc<dyn FakeClock>,
}

/// Builds a scripted engine (the donor's `MockEngine`): scripts that are already encoded,
/// the context, the pacing and the clock. The `pulsar-console` wiring encodes each script
/// text with the tokenizer and appends the end-of-turn id; this crate does not depend on
/// the tokenizer.
///
/// Behavior reference: project-maya serve/server.py:198-213 at 7e68a30f.
#[derive(Debug, Clone)]
pub struct FakeScript {
    scripts: Vec<Vec<u32>>,
    max_context: u32,
    delay: Duration,
    tok_s: Option<f64>,
    reload_delay: ReloadDelay,
    clock: Arc<dyn FakeClock>,
}

impl FakeScript {
    /// One script, repeated for every request.
    pub fn new(script: Vec<u32>) -> Self {
        Self::rotating(vec![script])
    }

    /// Several scripts: each request takes the next, and the last one repeats.
    pub fn rotating(scripts: Vec<Vec<u32>>) -> Self {
        Self {
            scripts,
            max_context: DEFAULT_MAX_CONTEXT,
            delay: Duration::ZERO,
            tok_s: None,
            reload_delay: ReloadDelay::Fixed(DEFAULT_RELOAD_DELAY),
            clock: Arc::new(SystemClock::new()),
        }
    }

    /// The context the engine reports (`READY <ctx>`); 0 means not ready.
    pub fn max_context(mut self, n: u32) -> Self {
        self.max_context = n;
        self
    }

    /// A fixed sleep before each token (the donor's `delay_s`).
    pub fn delay(mut self, d: Duration) -> Self {
        self.delay = d;
        self
    }

    /// Writes at about `tok_s` tokens a second with the donor's deterministic jitter, and
    /// reports its clock as figures (the donor's `tok_s`). `None` or 0 turns pacing off. A
    /// speed whose sleep `time.sleep` would refuse (see [`tok_s_from`]) is accepted, as the
    /// donor accepts it, and fails each paced generation at its first token.
    pub fn tok_s(mut self, tok_s: Option<f64>) -> Self {
        self.tok_s = tok_s;
        self
    }

    /// How long a context reload takes.
    pub fn reload_delay(mut self, d: Duration) -> Self {
        self.reload_delay = ReloadDelay::Fixed(d);
        self
    }

    /// The clock that paces the engine and times its figures.
    pub fn clock(mut self, clock: Arc<dyn FakeClock>) -> Self {
        self.clock = clock;
        self
    }

    /// Applies [`RELOAD_DELAY_ENV`] and [`TOK_S_ENV`] as `lookup` gives them (for the real
    /// environment, `|name| std::env::var(name).ok()`). An unset reload delay keeps the
    /// one already set; an unset speed keeps the one already set. The speed is read here,
    /// as the donor reads it at start, and a value `float()` refuses is an error. The
    /// reload delay's text is kept and read at each context reload, as the donor reads
    /// it there: a bad value fails that reload only (see [`reload_delay_from`]).
    pub fn apply_env(
        mut self,
        lookup: impl Fn(&str) -> Option<String>,
    ) -> Result<Self, FakeConfigError> {
        if let Some(v) = lookup(RELOAD_DELAY_ENV) {
            self.reload_delay = ReloadDelay::Text(v);
        }
        if let Some(v) = lookup(TOK_S_ENV) {
            self.tok_s = tok_s_from(Some(&v))?;
        }
        Ok(self)
    }

    /// Checks the limits.
    pub(crate) fn into_config(self) -> Result<FakeConfig, FakeConfigError> {
        if self.scripts.is_empty() {
            return Err(FakeConfigError::NoScript);
        }
        if self.scripts.len() > MAX_SCRIPTS {
            return Err(FakeConfigError::TooManyScripts {
                count: self.scripts.len(),
            });
        }
        if let Some((index, s)) = self
            .scripts
            .iter()
            .enumerate()
            .find(|(_, s)| s.len() > MAX_SCRIPT_TOKENS)
        {
            return Err(FakeConfigError::ScriptTooLong {
                index,
                len: s.len(),
            });
        }
        let tok_s = self.tok_s.and_then(no_pacing_at_zero);
        Ok(FakeConfig {
            scripts: self.scripts.into_iter().map(Arc::from).collect(),
            max_context: self.max_context,
            delay: self.delay,
            tok_s,
            reload_delay: self.reload_delay,
            clock: self.clock,
        })
    }

    /// The factory of this scripted engine.
    pub fn build(self) -> Result<FakeFactory, FakeConfigError> {
        FakeFactory::new(self)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fake_reload_delay_reads_like_python_float() {
        assert_eq!(reload_delay_from(None), Ok(Duration::from_secs(2)));
        assert_eq!(reload_delay_from(Some("0")), Ok(Duration::ZERO));
        assert_eq!(
            reload_delay_from(Some(" 0.25 ")),
            Ok(Duration::from_millis(250))
        );
        assert_eq!(reload_delay_from(Some("1_0")), Ok(Duration::from_secs(10)));
        let err = reload_delay_from(Some("soon")).unwrap_err();
        assert_eq!(
            err.to_string(),
            "PULSAR_CONSOLE_MOCK_RELOAD_S: could not convert string to float: 'soon'"
        );
        // An empty value is not "unset" here: float("") fails in the donor too.
        assert!(matches!(
            reload_delay_from(Some("")),
            Err(FakeConfigError::NotANumber { .. })
        ));
        // What `time.sleep` refuses, with its text.
        for (bad, reason) in [
            ("-1", "sleep length must be non-negative"),
            ("nan", "Invalid value NaN (not a number)"),
            ("inf", "timestamp too large to convert to C _PyTime_t"),
            ("-inf", "timestamp too large to convert to C _PyTime_t"),
            ("1e15", "timestamp too large to convert to C _PyTime_t"),
        ] {
            let err = reload_delay_from(Some(bad)).unwrap_err();
            assert_eq!(
                err,
                FakeConfigError::BadDuration {
                    name: RELOAD_DELAY_ENV,
                    value: bad.to_owned(),
                    reason
                },
                "{bad}"
            );
            assert_eq!(err.to_string(), format!("{RELOAD_DELAY_ENV}: {reason}"));
        }
        // -0.0 sleeps for nothing, as `time.sleep(-0.0)` does.
        assert_eq!(reload_delay_from(Some("-0.0")), Ok(Duration::ZERO));
    }

    #[test]
    fn fake_py_sleep_is_bounded_like_cpython() {
        assert_eq!(py_sleep(0.5), Ok(Duration::from_millis(500)));
        assert_eq!(py_sleep(-0.0), Ok(Duration::ZERO));
        // Just inside the range of `_PyTime_t` (about 292 years): accepted, bounded.
        let near = py_sleep(9.2e9).expect("within range");
        assert!(near < Duration::from_secs(9_300_000_000));
        // Past it, in either direction: refused, never an unbounded sleep.
        for s in [9.3e9, 8e299, f64::INFINITY, -9.3e9, f64::NEG_INFINITY] {
            assert_eq!(
                py_sleep(s),
                Err("timestamp too large to convert to C _PyTime_t"),
                "{s}"
            );
        }
        assert_eq!(py_sleep(-1.0), Err("sleep length must be non-negative"));
        assert_eq!(py_sleep(f64::NAN), Err("Invalid value NaN (not a number)"));
    }

    #[test]
    fn fake_tok_s_reads_like_the_donor() {
        assert_eq!(tok_s_from(None), Ok(None));
        assert_eq!(tok_s_from(Some("")), Ok(None));
        assert_eq!(tok_s_from(Some("0")), Ok(None));
        assert_eq!(tok_s_from(Some("0.0")), Ok(None));
        assert_eq!(tok_s_from(Some("40")), Ok(Some(40.0)));
        assert_eq!(tok_s_from(Some("1e2")), Ok(Some(100.0)));
        assert!(matches!(
            tok_s_from(Some("fast")),
            Err(FakeConfigError::NotANumber { .. })
        ));
        // `float(..) or None` keeps any other number: the donor fails such a speed only at
        // the first paced token, in `time.sleep` (see the factory's tests).
        assert_eq!(tok_s_from(Some("-3")), Ok(Some(-3.0)));
        assert_eq!(tok_s_from(Some("-0.0")), Ok(None));
        assert_eq!(tok_s_from(Some("inf")), Ok(Some(f64::INFINITY)));
        assert_eq!(tok_s_from(Some("1e-300")), Ok(Some(1e-300)));
        assert!(tok_s_from(Some("nan"))
            .expect("kept")
            .is_some_and(f64::is_nan));
    }

    #[test]
    fn fake_env_is_read_only_under_the_new_names() {
        let env = |name: &str| match name {
            "PULSAR_CONSOLE_MOCK_RELOAD_S" => Some("0.5".to_owned()),
            "PULSAR_CONSOLE_MOCK_TOK_S" => Some("20".to_owned()),
            _ => None,
        };
        let cfg = FakeScript::new(vec![1])
            .apply_env(env)
            .and_then(FakeScript::into_config)
            .expect("valid");
        assert_eq!(cfg.reload_delay, ReloadDelay::Text("0.5".to_owned()));
        assert_eq!(cfg.reload_delay.resolve(), Ok(Duration::from_millis(500)));
        assert_eq!(cfg.tok_s, Some(20.0));
        // A reload delay `float()` refuses does not stop the engine from being built: it
        // fails each context reload instead, as in the donor.
        let bad = |name: &str| (name == RELOAD_DELAY_ENV).then(String::new);
        let cfg = FakeScript::new(vec![1])
            .apply_env(bad)
            .and_then(FakeScript::into_config)
            .expect("built");
        assert!(matches!(
            cfg.reload_delay.resolve(),
            Err(FakeConfigError::NotANumber { .. })
        ));
        // A speed `float()` refuses is refused at build, as the donor fails at start.
        let fast = |name: &str| (name == TOK_S_ENV).then(|| "fast".to_owned());
        assert!(matches!(
            FakeScript::new(vec![1]).apply_env(fast),
            Err(FakeConfigError::NotANumber { .. })
        ));
        // The legacy names are not aliases (BRAND-1): setting only them changes nothing.
        let legacy = |name: &str| match name {
            "MAYA_MOCK_RELOAD_S" | "STRATA_MOCK_RELOAD_S" => Some("0".to_owned()),
            "MAYA_MOCK_TOK_S" | "STRATA_MOCK_TOK_S" => Some("20".to_owned()),
            _ => None,
        };
        let cfg = FakeScript::new(vec![1])
            .apply_env(legacy)
            .and_then(FakeScript::into_config)
            .expect("valid");
        assert_eq!(cfg.reload_delay, ReloadDelay::Fixed(DEFAULT_RELOAD_DELAY));
        assert_eq!(cfg.tok_s, None);
    }

    #[test]
    fn fake_script_limits_are_enforced() {
        assert_eq!(
            FakeScript::rotating(vec![]).into_config().unwrap_err(),
            FakeConfigError::NoScript
        );
        let many = vec![vec![1]; MAX_SCRIPTS + 1];
        assert_eq!(
            FakeScript::rotating(many).into_config().unwrap_err(),
            FakeConfigError::TooManyScripts {
                count: MAX_SCRIPTS + 1
            }
        );
        let long = vec![vec![1], vec![0; MAX_SCRIPT_TOKENS + 1]];
        assert_eq!(
            FakeScript::rotating(long).into_config().unwrap_err(),
            FakeConfigError::ScriptTooLong {
                index: 1,
                len: MAX_SCRIPT_TOKENS + 1
            }
        );
        // A NaN speed is kept, as the donor keeps it; it fails at the first paced token.
        let cfg = FakeScript::new(vec![1])
            .tok_s(Some(f64::NAN))
            .into_config()
            .expect("built");
        assert!(cfg.tok_s.is_some_and(f64::is_nan));
        let cfg = FakeScript::new(vec![1])
            .tok_s(Some(0.0))
            .into_config()
            .expect("valid");
        assert_eq!(
            cfg.tok_s, None,
            "a speed of 0 is no pacing, as `or None` reads it"
        );
    }
}
