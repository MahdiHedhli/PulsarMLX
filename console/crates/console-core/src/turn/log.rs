//! Log lines of the turn driver.
//!
//! Lead decision LD35: text that comes from an engine (an `ERR` message, a death note, a
//! `NOTE` line) or from a client is made log-safe before it is written to one of the
//! server's own log lines, so that it stays on one line. The lines go to a
//! [`FifoLog`](crate::fifo::FifoLog), the same sink the FIFO writes to, so that a test can
//! capture both in order.

/// The prefix of the server's own log lines (B2).
pub(crate) const LOG_PREFIX: &str = "[console]";

/// The text with every C0 control, DEL, C1 control, U+2028 and U+2029 escaped (`\n`, `\r`,
/// `\t`, any other as `\u{..}`), so that it stays on one log line. Other text is unchanged.
/// The same rule as `console_http::error`'s mid-answer line (LD35).
pub fn log_safe(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        match c {
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c.is_control() || c == '\u{2028}' || c == '\u{2029}' => {
                out.push_str(&format!("\\u{{{:x}}}", u32::from(c)));
            }
            c => out.push(c),
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn control_characters_are_escaped() {
        assert_eq!(log_safe("plain text"), "plain text");
        assert_eq!(log_safe("a\nb\rc\td"), "a\\nb\\rc\\td");
        assert_eq!(log_safe("x\u{1b}[2Jy"), "x\\u{1b}[2Jy");
        assert_eq!(
            log_safe("\u{7f}\u{85}\u{2028}\u{2029}"),
            "\\u{7f}\\u{85}\\u{2028}\\u{2029}"
        );
        assert_eq!(log_safe("été"), "été");
    }
}
