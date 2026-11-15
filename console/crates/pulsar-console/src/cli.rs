//! The command line of the minimal M1 entry point, read with Python `argparse`'s
//! conventions (CPython 3.14, lead decision LD38), as the donor's `main` reads its own.
//!
//! The options are the M1 subset of the donor's, in the donor's order: `--config`,
//! `--host`, `--script` (repeatable), `--port` (an integer, default 8095) and `--api-key`,
//! with `-h`/`--help`. The conventions built: long options, the `--opt=value` form, unique
//! prefix abbreviations (`allow_abbrev`), the last of a repeated option winning (except
//! `--script`, which appends), a value that looks like an option refused, a negative number
//! taken as a value (`-` then a digit, or `-.` then a digit), `--` and everything after
//! it reported among the unrecognized arguments, an ambiguous prefix refused only when the
//! parse reaches it, `-h` with text attached read as combined short flags, and every usage
//! error answered with the usage on standard error, then
//! `pulsar-console: error: <message>`, and the exit status 2. The rest of the donor's
//! options (`--engine`, `--gpu`, `--tokenizer`, `--open`, `--idle-unload`,
//! `--fit-max-tokens`, `--mcp-config`, `--parent-pipe`) are API-17's (M4); until then they
//! are unrecognized arguments. Colored output (Python 3.14 colors a terminal's usage
//! errors) is not reproduced, and the `--help` text is laid out for 80 columns whatever
//! `COLUMNS` says (the usage line in it does follow `COLUMNS`).
//!
//! Behavior reference: project-maya serve/server.py:7116-7146 at 7e68a30f.

use console_core::request::pyrepr::repr_str;

/// The program name in the usage and error lines.
pub const PROG: &str = "pulsar-console";

/// The donor's default port.
///
/// Behavior reference: project-maya serve/server.py:7126 at 7e68a30f.
pub const DEFAULT_PORT: i64 = 8095;

/// The option strings, in the order argparse registered them (`-h` and `--help` first).
const OPTION_STRINGS: [&str; 7] = [
    "-h",
    "--help",
    "--config",
    "--host",
    "--script",
    "--port",
    "--api-key",
];

/// The usage parts after the program name, in the donor's order.
const USAGE_PARTS: [&str; 6] = [
    "[-h]",
    "[--config CONFIG]",
    "[--host HOST]",
    "[--script SCRIPT]",
    "[--port PORT]",
    "[--api-key API_KEY]",
];

/// What the command line asked for.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Options {
    /// `--config`: the run config file.
    pub config: Option<String>,
    /// `--host`: the address to listen on (else the config's `host`, else `127.0.0.1`).
    pub host: Option<String>,
    /// `--script`, in order: the scripted engine's answers.
    pub scripts: Vec<String>,
    /// `--port`: an integer as Python's `int()` reads it; `None` when it does not fit 64
    /// bits (a port no socket takes).
    pub port: Option<i64>,
    /// `--api-key`, when given (else the environment's key, then the config's).
    pub api_key: Option<String>,
}

impl Default for Options {
    fn default() -> Self {
        Self {
            config: None,
            host: None,
            scripts: Vec::new(),
            port: Some(DEFAULT_PORT),
            api_key: None,
        }
    }
}

/// The outcome of reading the command line.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Parsed {
    /// Start the server with these options.
    Run(Options),
    /// `-h` or `--help`: print [`help`] on standard output and exit 0.
    Help,
}

/// A usage error: its message, printed after the usage as `pulsar-console: error:
/// <message>`, with the exit status 2.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UsageError(pub String);

/// argparse's `get_lines`: `parts` wrapped to `text_width`, each line starting with
/// `indent`; with `first_prefix`, the first line's indent is dropped and its length counts
/// the prefix instead.
fn usage_lines(
    parts: &[&str],
    indent: &str,
    first_prefix: Option<&str>,
    text_width: usize,
) -> Vec<String> {
    let mut lines: Vec<String> = Vec::new();
    let mut line: Vec<&str> = Vec::new();
    let mut line_len = first_prefix
        .map_or(indent.len(), str::len)
        .saturating_sub(1);
    for part in parts {
        if line_len + 1 + part.len() > text_width && !line.is_empty() {
            lines.push(format!("{indent}{}", line.join(" ")));
            line.clear();
            line_len = indent.len().saturating_sub(1);
        }
        line.push(part);
        line_len += part.len() + 1;
    }
    if !line.is_empty() {
        lines.push(format!("{indent}{}", line.join(" ")));
    }
    if first_prefix.is_some() {
        if let Some(first) = lines.first_mut() {
            *first = first.get(indent.len()..).unwrap_or("").to_owned();
        }
    }
    lines
}

/// The usage text (`usage: ...`), wrapped as argparse's `_format_usage` (CPython 3.14)
/// wraps it for a terminal `columns` wide (`COLUMNS`, else 80): the text width is
/// `columns - 2`. When `usage: pulsar-console` fits in three quarters of it, continuation
/// lines are indented under the first option; otherwise (fewer than 30 columns) the
/// program name stands alone on the first line and the options follow, indented by the
/// width of `usage: `.
pub fn usage(columns: usize) -> String {
    let text_width = columns.saturating_sub(2);
    let prefix = "usage: ";
    let one_line = format!("{PROG} {}", USAGE_PARTS.join(" "));
    if prefix.len() + one_line.len() <= text_width {
        return format!("{prefix}{one_line}");
    }
    // `len(prefix) + len(prog) <= 0.75 * text_width`, in integers.
    let lines = if 4 * (prefix.len() + PROG.len()) <= 3 * text_width {
        let indent = " ".repeat(prefix.len() + PROG.len() + 1);
        let parts: Vec<&str> = std::iter::once(PROG).chain(USAGE_PARTS).collect();
        usage_lines(&parts, &indent, Some(prefix), text_width)
    } else {
        let indent = " ".repeat(prefix.len());
        let mut lines = vec![PROG.to_owned()];
        lines.extend(usage_lines(&USAGE_PARTS, &indent, None, text_width));
        lines
    };
    format!("{prefix}{}", lines.join("\n"))
}

/// The usage error as it is printed on standard error: the usage, then the error line.
pub fn usage_error_text(error: &UsageError, columns: usize) -> String {
    format!("{}\n{PROG}: error: {}", usage(columns), error.0)
}

/// The `--help` text.
pub fn help(columns: usize) -> String {
    format!(
        "{}\n\n\
         PulsarMLX Console, minimal entry point of milestone M1: OpenAI Chat Completions\n\
         served from the scripted synthetic engine. No real model is served.\n\n\
         options:\n\
         \x20 -h, --help         show this help message and exit\n\
         \x20 --config CONFIG    the run config (JSON)\n\
         \x20 --host HOST        the address to listen on: 127.0.0.1 = this PC only (the\n\
         \x20                    default), 0.0.0.0 = also other devices on your network (set\n\
         \x20                    an API key); also \"host\" in the config\n\
         \x20 --script SCRIPT    the scripted engine's answer (default: a short greeting);\n\
         \x20                    given more than once, requests get them in turn and the\n\
         \x20                    last one repeats\n\
         \x20 --port PORT\n\
         \x20 --api-key API_KEY  require this key on /v1/* (Authorization: Bearer ... or\n\
         \x20                    x-api-key); several separated by commas; also\n\
         \x20                    $PULSAR_CONSOLE_API_KEY",
        usage(columns)
    )
}

/// The terminal width argparse uses: `COLUMNS` when it is a positive integer, else 80.
/// (CPython also asks the terminal; a server's output is rarely one, and the harness
/// never gives it one.)
pub fn columns_from(value: Option<&str>) -> usize {
    value
        .and_then(|v| v.trim().parse::<usize>().ok())
        .filter(|&c| c > 0)
        .unwrap_or(80)
}

/// One reading of an option-like argument (argparse's option tuple): the known option
/// it names (`None` for an option-like argument that matches none, which goes to the
/// extras), the separator before its explicit argument (`Some("=")`, `Some("")` for a
/// short option's attached text, or `None`) and that explicit argument.
#[derive(Debug, Clone, PartialEq, Eq)]
struct OptTuple {
    option: Option<&'static str>,
    sep: Option<&'static str>,
    explicit: Option<String>,
}

/// How argparse sees one argument before it consumes any (its `arg_strings_pattern`).
#[derive(Debug, Clone, PartialEq, Eq)]
enum Kind {
    /// `O`: an option-like argument with every option it could be (more than one is an
    /// ambiguous prefix, refused only when the parse loop reaches it).
    Opt(Vec<OptTuple>),
    /// `A`: a plain argument (every argument after the first `--` among them).
    Value,
    /// `-`: the first `--`.
    DoubleDash,
}

/// argparse's `_negative_number_matcher` of CPython 3.14, `-\.?\d` matched at the start:
/// such an argument is a value, because no option of this parser looks like a negative
/// number. (Python's `\d` also matches non-ASCII decimal digits; ASCII is read here.)
fn looks_negative(arg: &str) -> bool {
    let rest = arg.strip_prefix('-').unwrap_or("");
    let rest = rest.strip_prefix('.').unwrap_or(rest);
    arg.starts_with('-') && rest.starts_with(|c: char| c.is_ascii_digit())
}

fn known(option: &'static str, sep: Option<&'static str>, explicit: Option<String>) -> OptTuple {
    OptTuple {
        option: Some(option),
        sep,
        explicit,
    }
}

/// argparse's `_parse_optional` and `_get_option_tuples` (CPython 3.14): `None` for a
/// plain argument, else every reading of the option-like argument.
fn classify(arg: &str) -> Option<Vec<OptTuple>> {
    if !arg.starts_with('-') {
        return None;
    }
    if let Some(exact) = OPTION_STRINGS.iter().find(|o| **o == arg) {
        return Some(vec![known(exact, None, None)]);
    }
    if arg.len() == 1 {
        return None;
    }
    if let Some((name, value)) = arg.split_once('=') {
        if let Some(exact) = OPTION_STRINGS.iter().find(|o| **o == name) {
            return Some(vec![known(exact, Some("="), Some(value.to_owned()))]);
        }
    }
    let tuples: Vec<OptTuple> = if arg.starts_with("--") {
        let (prefix, sep, explicit) = match arg.split_once('=') {
            Some((p, v)) => (p, Some("="), Some(v.to_owned())),
            None => (arg, None, None),
        };
        OPTION_STRINGS
            .iter()
            .filter(|o| o.starts_with(prefix))
            .map(|o| known(o, sep, explicit.clone()))
            .collect()
    } else {
        // A single dash: `-h` followed by text is `-h` with that text attached.
        let split = arg.char_indices().nth(2).map_or(arg.len(), |(i, _)| i);
        let (short, rest) = arg.split_at(split);
        OPTION_STRINGS
            .iter()
            .filter_map(|o| {
                if *o == short {
                    Some(known(o, Some(""), Some(rest.to_owned())))
                } else if o.starts_with(arg) {
                    Some(known(o, None, None))
                } else {
                    None
                }
            })
            .collect()
    };
    if !tuples.is_empty() {
        return Some(tuples);
    }
    if looks_negative(arg) || arg.contains(' ') {
        return None;
    }
    Some(vec![OptTuple {
        option: None,
        sep: None,
        explicit: None,
    }])
}

/// argparse's argument pattern: everything after the first `--` is a plain argument and
/// is not classified.
fn pattern(args: &[String]) -> Vec<Kind> {
    let mut kinds = Vec::with_capacity(args.len());
    let mut rest = args.iter();
    for arg in rest.by_ref() {
        if arg == "--" {
            kinds.push(Kind::DoubleDash);
            break;
        }
        kinds.push(classify(arg).map_or(Kind::Value, Kind::Opt));
    }
    kinds.extend(rest.map(|_| Kind::Value));
    kinds
}

/// The name argparse gives an option in its errors.
fn display_name(option: &str) -> &str {
    match option {
        "-h" | "--help" => "-h/--help",
        other => other,
    }
}

/// Python's `int(text)` for a command-line value: surrounding whitespace, an optional sign,
/// ASCII digits with single `_` between them. `Ok(None)` for a valid integer beyond 64
/// bits; `Err(())` where Python raises `ValueError`. (Python also reads non-ASCII decimal
/// digits; they are refused here.)
fn py_int(text: &str) -> Result<Option<i64>, ()> {
    let s = console_pyjson::pystr::strip(text, None);
    let (negative, digits) = match s.strip_prefix('-') {
        Some(rest) => (true, rest),
        None => (false, s.strip_prefix('+').unwrap_or(s)),
    };
    if digits.is_empty()
        || digits.starts_with('_')
        || digits.ends_with('_')
        || digits.contains("__")
    {
        return Err(());
    }
    if !digits.chars().all(|c| c.is_ascii_digit() || c == '_') {
        return Err(());
    }
    let clean: String = digits.chars().filter(|c| *c != '_').collect();
    let magnitude = match clean.parse::<i64>() {
        Ok(v) => v,
        Err(_) => return Ok(None),
    };
    Ok(Some(if negative { -magnitude } else { magnitude }))
}

/// What one option consumed: help (which exits before anything else is looked at), or a
/// value for a valued option.
enum Taken {
    Help,
    Value(&'static str, String),
}

/// argparse's `consume_optional` (CPython 3.14) for the option-like argument at `start`:
/// the index after what it consumed, and what it took (`None` for an unknown option,
/// which goes to `extras`).
fn consume_optional(
    args: &[String],
    kinds: &[Kind],
    start: usize,
    tuples: &[OptTuple],
    extras: &mut Vec<String>,
) -> Result<(usize, Option<Taken>), UsageError> {
    if tuples.len() > 1 {
        let names: Vec<&str> = tuples.iter().filter_map(|t| t.option).collect();
        return Err(UsageError(format!(
            "ambiguous option: {} could match {}",
            args.get(start).map_or("", String::as_str),
            names.join(", ")
        )));
    }
    let Some(first) = tuples.first() else {
        return Ok((start + 1, None));
    };
    let mut option = first.option;
    let mut sep = first.sep;
    let mut explicit = first.explicit.clone();
    let mut help = false;
    loop {
        let Some(action) = option else {
            if let Some(arg) = args.get(start) {
                extras.push(arg.clone());
            }
            return Ok((start + 1, help.then_some(Taken::Help)));
        };
        let is_help = action == "-h" || action == "--help";
        match explicit.take() {
            Some(text) => {
                let long = action.starts_with("--");
                if is_help && !long && !text.is_empty() {
                    // `-h` with text attached: combined short flags (`-hh`), unless the
                    // text came after `=` or starts with a dash.
                    if sep == Some("=") || text.starts_with('-') {
                        return Err(UsageError(format!(
                            "argument {}: ignored explicit argument {}",
                            display_name(action),
                            repr_str(&text)
                        )));
                    }
                    help = true;
                    let mut chars = text.chars();
                    let c = chars.next().unwrap_or('-');
                    let rest = chars.as_str();
                    let flag = format!("-{c}");
                    match OPTION_STRINGS.iter().find(|o| **o == flag) {
                        Some(next) => {
                            option = Some(next);
                            if rest.is_empty() {
                                sep = None;
                                explicit = None;
                            } else if let Some(after) = rest.strip_prefix('=') {
                                sep = Some("=");
                                explicit = Some(after.to_owned());
                            } else {
                                sep = Some("");
                                explicit = Some(rest.to_owned());
                            }
                        }
                        None => {
                            // An unknown flag goes to the extras, which help never reports.
                            extras.push(format!("-{text}"));
                            return Ok((start + 1, Some(Taken::Help)));
                        }
                    }
                } else if !is_help {
                    return Ok((start + 1, Some(Taken::Value(action, text))));
                } else {
                    return Err(UsageError(format!(
                        "argument {}: ignored explicit argument {}",
                        display_name(action),
                        repr_str(&text)
                    )));
                }
            }
            None if is_help => return Ok((start + 1, Some(Taken::Help))),
            None => {
                return match (args.get(start + 1), kinds.get(start + 1)) {
                    (Some(v), Some(Kind::Value)) => {
                        let taken = if help {
                            Taken::Help
                        } else {
                            Taken::Value(action, v.clone())
                        };
                        Ok((start + 2, Some(taken)))
                    }
                    _ => Err(UsageError(format!(
                        "argument {}: expected one argument",
                        display_name(action)
                    ))),
                };
            }
        }
    }
}

/// Reads the command line (without the program name), as CPython 3.14's
/// `_parse_known_args2` reads it: options are consumed left to right, plain arguments and
/// unknown options collect in the extras, and everything from the first `--` on (the `--`
/// itself included) is an extra, so any of them is `unrecognized arguments: ...`.
pub fn parse(args: &[String]) -> Result<Parsed, UsageError> {
    let kinds = pattern(args);
    let mut opts = Options::default();
    let mut extras: Vec<String> = Vec::new();
    let last_option = kinds.iter().rposition(|k| matches!(k, Kind::Opt(_)));
    let mut i = 0;
    while let (Some(last), Some(kind)) = (last_option, kinds.get(i)) {
        if i > last {
            break;
        }
        let Kind::Opt(tuples) = kind else {
            if let Some(arg) = args.get(i) {
                extras.push(arg.clone());
            }
            i += 1;
            continue;
        };
        let (next, taken) = consume_optional(args, &kinds, i, tuples, &mut extras)?;
        i = next;
        match taken {
            None => {}
            Some(Taken::Help) => return Ok(Parsed::Help),
            Some(Taken::Value(option, value)) => match option {
                "--config" => opts.config = Some(value),
                "--host" => opts.host = Some(value),
                "--script" => opts.scripts.push(value),
                "--api-key" => opts.api_key = Some(value),
                _ => {
                    opts.port = py_int(&value).map_err(|()| {
                        UsageError(format!(
                            "argument --port: invalid int value: {}",
                            repr_str(&value)
                        ))
                    })?;
                }
            },
        }
    }
    extras.extend(args.iter().skip(i).cloned());
    if !extras.is_empty() {
        return Err(UsageError(format!(
            "unrecognized arguments: {}",
            extras.join(" ")
        )));
    }
    Ok(Parsed::Run(opts))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn run(args: &[&str]) -> Result<Parsed, UsageError> {
        parse(&args.iter().map(|a| (*a).to_owned()).collect::<Vec<_>>())
    }

    fn opts(args: &[&str]) -> Options {
        match run(args) {
            Ok(Parsed::Run(o)) => o,
            other => panic!("{args:?}: {other:?}"),
        }
    }

    fn error(args: &[&str]) -> String {
        match run(args) {
            Err(UsageError(m)) => m,
            other => panic!("{args:?}: {other:?}"),
        }
    }

    #[test]
    fn defaults_forms_and_abbreviations() {
        assert_eq!(opts(&[]), Options::default());
        assert_eq!(opts(&[]).port, Some(8095));
        let o = opts(&[
            "--port=0",
            "--host",
            "0.0.0.0",
            "--scr",
            "a",
            "--script=b",
            "--api=k1",
            "--conf",
            "pulsar-x.json",
        ]);
        assert_eq!(o.port, Some(0));
        assert_eq!(o.host.as_deref(), Some("0.0.0.0"));
        assert_eq!(o.scripts, vec!["a".to_owned(), "b".to_owned()]);
        assert_eq!(o.api_key.as_deref(), Some("k1"));
        assert_eq!(o.config.as_deref(), Some("pulsar-x.json"));
        // The last of a repeated option wins; int() reads whitespace, a sign, underscores.
        assert_eq!(opts(&["--port", "1", "--port", " +8_0 "]).port, Some(80));
        // A negative number is a value; a port beyond 64 bits is kept as no port.
        assert_eq!(opts(&["--port", "-5"]).port, Some(-5));
        assert_eq!(opts(&["--port", "99999999999999999999"]).port, None);
        // An empty value after `=` is a value.
        assert_eq!(opts(&["--api-key="]).api_key.as_deref(), Some(""));
        // A value with a space that starts with a dash is a value.
        assert_eq!(opts(&["--script", "-a b"]).scripts, vec!["-a b".to_owned()]);
        assert_eq!(run(&["--help"]), Ok(Parsed::Help));
        assert_eq!(run(&["--he"]), Ok(Parsed::Help));
        assert_eq!(run(&["-h", "--bogus"]), Ok(Parsed::Help));
    }

    #[test]
    fn usage_errors_have_argparse_messages() {
        assert_eq!(
            error(&["--port", "abc"]),
            "argument --port: invalid int value: 'abc'"
        );
        assert_eq!(
            error(&["--port="]),
            "argument --port: invalid int value: ''"
        );
        assert_eq!(
            error(&["--port", "1__0"]),
            "argument --port: invalid int value: '1__0'"
        );
        assert_eq!(error(&["--port"]), "argument --port: expected one argument");
        assert_eq!(
            error(&["--host", "--port", "1"]),
            "argument --host: expected one argument"
        );
        assert_eq!(
            error(&["--host", "-x"]),
            "argument --host: expected one argument"
        );
        assert_eq!(
            error(&["--h"]),
            "ambiguous option: --h could match --help, --host"
        );
        assert_eq!(
            error(&["--gpu", "0", "--engine=line"]),
            "unrecognized arguments: --gpu 0 --engine=line"
        );
        assert_eq!(error(&["extra"]), "unrecognized arguments: extra");
        assert_eq!(error(&["-x"]), "unrecognized arguments: -x");
        assert_eq!(
            error(&["--help=1"]),
            "argument -h/--help: ignored explicit argument '1'"
        );
        assert_eq!(
            error(&["-h=1"]),
            "argument -h/--help: ignored explicit argument '1'"
        );
        assert_eq!(
            error(&["-h="]),
            "argument -h/--help: ignored explicit argument ''"
        );
        assert_eq!(
            error(&["-h-x"]),
            "argument -h/--help: ignored explicit argument '-x'"
        );
        assert_eq!(
            error(&["-hh=1"]),
            "argument -h/--help: ignored explicit argument '1'"
        );
        // A type error comes before the unrecognized arguments, in argument order.
        assert_eq!(
            error(&["--gpu", "--port", "z"]),
            "argument --port: invalid int value: 'z'"
        );
    }

    /// Expected strings recorded with CPython 3.14.7's standard-library argparse, set up
    /// with the same five options and `prog="pulsar-console"` (lead decision LD38).
    #[test]
    fn cpython_3_14_cases_of_double_dash_negatives_and_combined_flags() {
        // `--` and everything after it are extras, listed with the `--`; nothing after it
        // is classified.
        assert_eq!(error(&["--port", "0", "--"]), "unrecognized arguments: --");
        assert_eq!(error(&["--port", "1", "--"]), "unrecognized arguments: --");
        assert_eq!(
            error(&["--", "--port"]),
            "unrecognized arguments: -- --port"
        );
        assert_eq!(error(&["--", "x"]), "unrecognized arguments: -- x");
        assert_eq!(error(&["--", "--h"]), "unrecognized arguments: -- --h");
        assert_eq!(
            error(&["--script", "a", "--", "b"]),
            "unrecognized arguments: -- b"
        );
        assert_eq!(
            error(&["--port", "--"]),
            "argument --port: expected one argument"
        );
        // An ambiguous prefix is refused only when the parse reaches it.
        assert_eq!(run(&["-h", "--h"]), Ok(Parsed::Help));
        assert_eq!(
            error(&["--port", "z", "--h"]),
            "argument --port: invalid int value: 'z'"
        );
        // `-` then a digit (or `-.` then a digit) is a value.
        assert_eq!(
            error(&["--port", "-5x"]),
            "argument --port: invalid int value: '-5x'"
        );
        assert_eq!(
            error(&["--port", "-1e5"]),
            "argument --port: invalid int value: '-1e5'"
        );
        assert_eq!(
            error(&["--port", "-.5"]),
            "argument --port: invalid int value: '-.5'"
        );
        assert_eq!(opts(&["--host", "-1x"]).host.as_deref(), Some("-1x"));
        assert_eq!(error(&["-1x"]), "unrecognized arguments: -1x");
        assert_eq!(error(&["-.5"]), "unrecognized arguments: -.5");
        assert_eq!(
            error(&["x", "--port", "1", "y"]),
            "unrecognized arguments: x y"
        );
        // Combined short flags: help runs first and the unknown rest is never reported.
        assert_eq!(run(&["-hh"]), Ok(Parsed::Help));
        assert_eq!(run(&["-hx"]), Ok(Parsed::Help));
        assert_eq!(run(&["-hhost"]), Ok(Parsed::Help));
    }

    #[test]
    fn the_usage_wraps_as_argparse_wraps_it() {
        assert_eq!(
            usage(80),
            "usage: pulsar-console [-h] [--config CONFIG] [--host HOST] [--script SCRIPT]\n                      [--port PORT] [--api-key API_KEY]"
        );
        assert_eq!(
            usage(200),
            "usage: pulsar-console [-h] [--config CONFIG] [--host HOST] [--script SCRIPT] [--port PORT] [--api-key API_KEY]"
        );
        assert_eq!(
            usage_error_text(&UsageError("x".into()), 200),
            "usage: pulsar-console [-h] [--config CONFIG] [--host HOST] [--script SCRIPT] [--port PORT] [--api-key API_KEY]\npulsar-console: error: x"
        );
        // Below 30 columns the program name stands alone (CPython 3.14.7).
        let alone = "usage: pulsar-console\n       [-h]\n       [--config CONFIG]\n       [--host HOST]\n       [--script SCRIPT]\n       [--port PORT]\n       [--api-key API_KEY]";
        assert_eq!(usage(20), alone);
        assert_eq!(usage(25), alone);
        assert_eq!(usage(29), alone);
        assert_eq!(
            usage(30),
            "usage: pulsar-console [-h]\n                      [--config CONFIG]\n                      [--host HOST]\n                      [--script SCRIPT]\n                      [--port PORT]\n                      [--api-key API_KEY]"
        );
        assert_eq!(columns_from(None), 80);
        assert_eq!(columns_from(Some("120")), 120);
        assert_eq!(columns_from(Some("0")), 80);
        assert_eq!(columns_from(Some("wide")), 80);
        assert!(help(80).starts_with("usage: pulsar-console [-h]"));
        assert!(help(80).contains("No real model is served."));
    }
}
