//! The JSON in an answer that was asked for JSON (`response_format` `json_object` or
//! `json_schema`).
//!
//! Behavior reference: project-maya serve/server.py:4909-4930 at 7e68a30f.

use console_pyjson::loads::{loads, raw_decode_bytes};
use console_pyjson::pystr::{is_space, strip};

/// The body of the first code fence of `s` as the donor's pattern
/// ``` r"```(?:json)?\s*\n(.*?)```" ``` with `re.S` finds it: three backticks, an optional
/// `json`, whitespace that holds a line feed (the body starts after the last line feed of
/// that whitespace, as the greedy `\s*` backtracks to it), then everything up to the next
/// three backticks. `None` when no fence matches.
fn first_fence(s: &str) -> Option<&str> {
    let mut from = 0;
    while let Some(found) = s.get(from..).and_then(|rest| rest.find("```")) {
        let start = from + found;
        let after = start + 3;
        let rest = s.get(after..).unwrap_or("");
        // `(?:json)?` is greedy: with `json` first, then without it.
        let variants: &[usize] = if rest.starts_with("json") {
            &[4, 0]
        } else {
            &[0]
        };
        for &skip in variants {
            let open = after + skip;
            let tail = s.get(open..).unwrap_or("");
            let run_len: usize = tail
                .chars()
                .take_while(|c| is_space(*c))
                .map(char::len_utf8)
                .sum();
            let run = tail.get(..run_len).unwrap_or("");
            let Some(nl) = run.rfind('\n') else {
                continue;
            };
            let body_start = open + nl + 1;
            let body = s.get(body_start..).unwrap_or("");
            if let Some(end) = body.find("```") {
                return body.get(..end);
            }
        }
        from = start + 1;
    }
    None
}

/// The JSON in an answer: the stripped answer itself when it parses, else the stripped
/// inside of its first code fence when that parses, else the first object or array that
/// decodes starting at any `[` or `{`; the text as it was when none parses.
///
/// Behavior reference: project-maya serve/server.py:4909-4930 at 7e68a30f.
pub fn json_from_text(text: &str) -> String {
    let s = strip(text, None);
    let mut candidates = vec![s];
    if let Some(fence) = first_fence(s) {
        candidates.push(strip(fence, None));
    }
    for c in candidates {
        if loads(c).is_ok() {
            return c.to_owned();
        }
    }
    for (i, ch) in s.char_indices() {
        if ch != '[' && ch != '{' {
            continue;
        }
        if let Ok((_, end)) = raw_decode_bytes(s, i) {
            if let Some(found) = s.get(i..end) {
                return found.to_owned();
            }
        }
    }
    text.to_owned()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_answer_itself_a_fence_or_the_first_value() {
        assert_eq!(json_from_text("  {\"a\": 1}\n"), "{\"a\": 1}");
        assert_eq!(
            json_from_text("Here:\n```json\n{\"a\": [1, 2]}\n```\nDone."),
            "{\"a\": [1, 2]}"
        );
        assert_eq!(json_from_text("```\n[1]\n```"), "[1]");
        // A fence whose body does not parse: the first decodable value after it.
        assert_eq!(
            json_from_text("```json\nnot json {\"b\": 2} tail\n```"),
            "{\"b\": 2}"
        );
        // The first `[` or `{` that decodes wins, not the longest.
        assert_eq!(json_from_text("x [oops {\"c\": 3} [4]"), "{\"c\": 3}");
        // Nothing parses: the text as it was, whitespace kept.
        assert_eq!(json_from_text(" no json here "), " no json here ");
        assert_eq!(json_from_text(""), "");
        // A bare number or string is JSON too (json.loads takes it).
        assert_eq!(json_from_text(" 42 "), "42");
    }

    #[test]
    fn the_fence_pattern_follows_the_regular_expression() {
        // `\s*\n`: the body starts after the last line feed of the whitespace run.
        assert_eq!(first_fence("```json \n\n  x```"), Some("  x"));
        // `json` not followed by whitespace with a line feed: no fence at that place, and
        // the pattern tries the next position.
        assert_eq!(first_fence("```jsonx\n1```"), None);
        assert_eq!(first_fence("````json\n1```"), Some("1"));
        // No closing fence: no match.
        assert_eq!(first_fence("```\nopen"), None);
        // A fence without a line feed after it does not match.
        assert_eq!(first_fence("```{}```"), None);
    }
}
