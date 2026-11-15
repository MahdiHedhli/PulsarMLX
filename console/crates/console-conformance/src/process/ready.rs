//! The ready line: the line a server prints on standard output once it accepts
//! connections. The contract is `specs/022-console-serving-parity/contracts/cli.md`.
//!
//! The server form is the donor's, byte for byte:
//!
//! ```text
//! ready: http://<here>:<port>/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context <N> tokens[, images on][, API key required])
//! ```
//!
//! `<here>` is printed as is, without brackets for an IPv6 address, as the donor prints
//! it. A synthetic-backend marker on this line is only proposed (PLAN-1, FR-050,
//! OPEN-35): the parser accepts the line with nothing after the closing parenthesis, or
//! with one suffix after it, separated by whitespace, and records the suffix without
//! judging its text.
//!
//! The oracle form, `CNF-READY port=<n>`, is printed by the oracle driver of CNF-08
//! (tasks/conformance.md, CNF-08); the harness accepts it only when asked to.
//!
//! Behavior reference: project-maya serve/server.py:7385-7390 at 7e68a30f.

use std::net::{IpAddr, Ipv4Addr, SocketAddr};

use super::ProcessError;

/// The start of the server form.
pub const SERVER_PREFIX: &str = "ready: http://";

/// The start of the oracle form.
pub const ORACLE_PREFIX: &str = "CNF-READY port=";

/// What follows the port in the server form, up to the context size.
const ROUTES: &str =
    "/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context ";

/// The parts of a ready line in the server form.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReadyLine {
    /// The address as printed (`127.0.0.1` for a wildcard bind).
    pub host: String,
    /// The port.
    pub port: u16,
    /// The context size in tokens.
    pub context_tokens: u64,
    /// `, images on` was present.
    pub images_on: bool,
    /// `, API key required` was present.
    pub api_key_required: bool,
    /// The text after the closing parenthesis, trimmed, when there is any: the place of
    /// the proposed synthetic marker (PLAN-1, OPEN-35).
    pub suffix: Option<String>,
}

/// A parsed ready line.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Ready {
    /// The server form.
    Server(ReadyLine),
    /// The oracle form.
    Oracle {
        /// The port.
        port: u16,
    },
}

impl Ready {
    /// The port the line names.
    pub fn port(&self) -> u16 {
        match self {
            Ready::Server(line) => line.port,
            Ready::Oracle { port } => *port,
        }
    }

    /// The loopback address to connect to: the printed host when it is a loopback IP
    /// address (or `localhost`), `127.0.0.1` for the oracle form. Any other host is
    /// refused, because the harness only ever talks to loopback.
    pub fn loopback_addr(&self) -> Result<SocketAddr, ProcessError> {
        let ip = match self {
            Ready::Oracle { .. } => IpAddr::V4(Ipv4Addr::LOCALHOST),
            Ready::Server(line) if line.host == "localhost" => IpAddr::V4(Ipv4Addr::LOCALHOST),
            Ready::Server(line) => match line.host.parse::<IpAddr>() {
                Ok(ip) if ip.is_loopback() => ip,
                _ => {
                    return Err(ProcessError::NotLoopback {
                        host: line.host.clone(),
                        transcript: String::new(),
                        run_dir: None,
                    })
                }
            },
        };
        Ok(SocketAddr::new(ip, self.port()))
    }
}

/// Which ready forms the harness accepts.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ReadyExpect {
    /// The server form only (the default).
    #[default]
    Server,
    /// The oracle form only.
    Oracle,
    /// Either form.
    Either,
}

impl ReadyExpect {
    /// Whether `line` starts like a ready line of an accepted form; such a line must then
    /// parse, or the harness reports it as malformed.
    pub fn claims(self, line: &str) -> bool {
        let server = line.starts_with("ready:");
        let oracle = line.starts_with("CNF-READY");
        match self {
            ReadyExpect::Server => server,
            ReadyExpect::Oracle => oracle,
            ReadyExpect::Either => server || oracle,
        }
    }
}

/// Parses `line` (without its line end) as a ready line of an accepted form; `None` when
/// it is not one.
pub fn parse_ready(line: &str, expect: ReadyExpect) -> Option<Ready> {
    match expect {
        ReadyExpect::Server => parse_server(line).map(Ready::Server),
        ReadyExpect::Oracle => parse_oracle(line),
        ReadyExpect::Either => parse_server(line)
            .map(Ready::Server)
            .or_else(|| parse_oracle(line)),
    }
}

fn parse_oracle(line: &str) -> Option<Ready> {
    let digits = line.strip_prefix(ORACLE_PREFIX)?;
    Some(Ready::Oracle {
        port: decimal_port(digits)?,
    })
}

fn decimal_port(digits: &str) -> Option<u16> {
    if digits.is_empty() || digits.len() > 5 || !digits.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    digits.parse().ok()
}

fn parse_server(line: &str) -> Option<ReadyLine> {
    let rest = line.strip_prefix(SERVER_PREFIX)?;
    let at = rest.find(ROUTES)?;
    let (address, tail) = rest.split_at(at);
    let tail = tail.get(ROUTES.len()..)?;
    // `<here>:<port>`; the host may itself hold colons (an IPv6 address printed bare).
    let (host, port) = address.rsplit_once(':')?;
    if host.is_empty() || host.contains(char::is_whitespace) {
        return None;
    }
    let port = decimal_port(port)?;
    let digits_end = tail
        .bytes()
        .position(|b| !b.is_ascii_digit())
        .unwrap_or(tail.len());
    let (digits, tail) = tail.split_at(digits_end);
    if digits.is_empty() || (digits.len() > 1 && digits.starts_with('0')) {
        return None;
    }
    let context_tokens: u64 = digits.parse().ok()?;
    let mut tail = tail.strip_prefix(" tokens")?;
    let mut images_on = false;
    if let Some(t) = tail.strip_prefix(", images on") {
        images_on = true;
        tail = t;
    }
    let mut api_key_required = false;
    if let Some(t) = tail.strip_prefix(", API key required") {
        api_key_required = true;
        tail = t;
    }
    let after = tail.strip_prefix(')')?;
    let suffix = if after.is_empty() {
        None
    } else if after.starts_with(char::is_whitespace) && !after.trim().is_empty() {
        Some(after.trim().to_string())
    } else {
        return None;
    };
    Some(ReadyLine {
        host: host.to_string(),
        port,
        context_tokens,
        images_on,
        api_key_required,
        suffix,
    })
}

/// The ready line in the server form, as the donor prints it; the inverse of
/// [`parse_ready`] for [`ReadyExpect::Server`]. Used by the test child and by tests.
pub fn format_server_line(line: &ReadyLine) -> String {
    let mut out = format!(
        "{SERVER_PREFIX}{}:{}{ROUTES}{} tokens",
        line.host, line.port, line.context_tokens
    );
    if line.images_on {
        out.push_str(", images on");
    }
    if line.api_key_required {
        out.push_str(", API key required");
    }
    out.push(')');
    if let Some(suffix) = &line.suffix {
        out.push_str("  ");
        out.push_str(suffix);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    const DONOR: &str = "ready: http://127.0.0.1:8095/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context 32768 tokens)";

    fn server(line: &str) -> Option<ReadyLine> {
        match parse_ready(line, ReadyExpect::Server) {
            Some(Ready::Server(l)) => Some(l),
            _ => None,
        }
    }

    #[test]
    fn the_donor_line_parses() {
        let l = server(DONOR).unwrap();
        assert_eq!(l.host, "127.0.0.1");
        assert_eq!(l.port, 8095);
        assert_eq!(l.context_tokens, 32768);
        assert!(!l.images_on && !l.api_key_required);
        assert_eq!(l.suffix, None);
        assert_eq!(format_server_line(&l), DONOR);
    }

    #[test]
    fn optional_clauses_in_the_donor_order() {
        let both = DONOR.replace(" tokens)", " tokens, images on, API key required)");
        let l = server(&both).unwrap();
        assert!(l.images_on && l.api_key_required);
        assert_eq!(format_server_line(&l), both);
        let key = DONOR.replace(" tokens)", " tokens, API key required)");
        let l = server(&key).unwrap();
        assert!(!l.images_on && l.api_key_required);
        // the donor never prints them the other way round
        let swapped = DONOR.replace(" tokens)", " tokens, API key required, images on)");
        assert_eq!(server(&swapped), None);
    }

    #[test]
    fn a_suffix_after_the_parenthesis_is_accepted_and_recorded() {
        // PLAN-1 / OPEN-35: the marker is proposed, its text undecided
        let marked = format!("{DONOR}  [synthetic backend]");
        let l = server(&marked).unwrap();
        assert_eq!(l.suffix.as_deref(), Some("[synthetic backend]"));
        assert_eq!(format_server_line(&l), marked);
        // glued to the parenthesis, or whitespace only, is not a suffix
        assert_eq!(server(&format!("{DONOR}x")), None);
        assert_eq!(server(&format!("{DONOR}   ")), None);
    }

    #[test]
    fn an_ipv6_host_is_printed_bare_as_the_donor_does() {
        let line = DONOR.replace("127.0.0.1", "::1");
        let l = server(&line).unwrap();
        assert_eq!(l.host, "::1");
        assert_eq!(l.port, 8095);
        let ready = Ready::Server(l);
        assert_eq!(ready.loopback_addr().unwrap().to_string(), "[::1]:8095");
    }

    #[test]
    fn malformed_lines_do_not_parse() {
        for bad in [
            "ready: http://127.0.0.1/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context 1 tokens)",
            "ready: http://127.0.0.1:99999/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context 1 tokens)",
            "ready: http://127.0.0.1:80/v1 (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context 1 tokens)",
            "ready: http://127.0.0.1:80/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context  tokens)",
            "ready: http://127.0.0.1:80/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context 01 tokens)",
            "ready: http://127.0.0.1:80/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context 1 tokens",
            "ready: http://127.0.0.1:+80/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context 1 tokens)",
            "ready: http://:80/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context 1 tokens)",
            " ready: http://127.0.0.1:80/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context 1 tokens)",
            "",
        ] {
            assert_eq!(server(bad), None, "{bad}");
        }
    }

    #[test]
    fn the_oracle_form_only_when_asked() {
        assert_eq!(
            parse_ready("CNF-READY port=40123", ReadyExpect::Oracle),
            Some(Ready::Oracle { port: 40123 })
        );
        assert_eq!(
            parse_ready("CNF-READY port=40123", ReadyExpect::Server),
            None
        );
        assert_eq!(
            parse_ready("CNF-READY port=40123", ReadyExpect::Either).map(|r| r.port()),
            Some(40123)
        );
        assert!(parse_ready(DONOR, ReadyExpect::Either).is_some());
        assert_eq!(parse_ready(DONOR, ReadyExpect::Oracle), None);
        for bad in [
            "CNF-READY port=",
            "CNF-READY port=1 ",
            "CNF-READY port=70000",
            "CNF-READY port=x",
        ] {
            assert_eq!(parse_ready(bad, ReadyExpect::Oracle), None, "{bad}");
        }
    }

    #[test]
    fn claims_marks_lines_that_must_parse() {
        assert!(ReadyExpect::Server.claims("ready: nonsense"));
        assert!(!ReadyExpect::Server.claims("CNF-READY port=1"));
        assert!(ReadyExpect::Either.claims("CNF-READY port=1"));
        assert!(!ReadyExpect::Server.claims("[console] already ready: no"));
    }

    #[test]
    fn only_loopback_addresses_are_returned() {
        let mut l = server(DONOR).unwrap();
        assert_eq!(
            Ready::Server(l.clone())
                .loopback_addr()
                .unwrap()
                .to_string(),
            "127.0.0.1:8095"
        );
        l.host = "localhost".into();
        assert!(Ready::Server(l.clone()).loopback_addr().is_ok());
        l.host = "192.0.2.7".into();
        assert!(matches!(
            Ready::Server(l).loopback_addr(),
            Err(ProcessError::NotLoopback { .. })
        ));
    }
}
