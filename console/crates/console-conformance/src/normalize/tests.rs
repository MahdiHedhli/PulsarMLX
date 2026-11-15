//! Unit tests of the normalizer's private helpers. The behavior of the whole normalizer,
//! and the negative self-tests, are in `tests/cnf04_*.rs`.

use super::*;

#[test]
fn edits_apply_in_order_and_skip_overlaps() {
    let edits = vec![
        Edit {
            start: 4,
            end: 5,
            text: "X".into(),
        },
        Edit {
            start: 0,
            end: 1,
            text: "<a>".into(),
        },
        Edit {
            start: 4,
            end: 6,
            text: "never".into(),
        },
    ];
    assert_eq!(apply_edits("abcdefg", edits), "<a>bcdXfg");
    // an edit that does not fall on character boundaries is dropped
    let edits = vec![Edit {
        start: 1,
        end: 2,
        text: "x".into(),
    }];
    assert_eq!(apply_edits("\u{e9}a", edits), "\u{e9}a");
}

#[test]
fn sse_data_lines_follow_the_event_stream_rules() {
    let raw = "event: x\r\ndata: {\"a\":\r\ndata:1}\n: note\ndata\n\n";
    let lines = sse_data_lines(raw, 10);
    let got: Vec<(usize, &str)> = lines;
    assert_eq!(got, [(10 + 16, "{\"a\":"), (10 + 28, "1}"), (10 + 42, "")]);
    // a byte-order mark at the very start of the body is not part of the field name
    let bom = "\u{feff}data: 1\n\n";
    assert_eq!(sse_data_lines(bom, 0), [(9, "1")]);
    // elsewhere it is
    assert!(sse_data_lines(bom, 5).is_empty());
}

#[test]
fn raw_header_values_are_found_once_and_unfolded() {
    let head = "HTTP/1.0 200 OK\r\nServer: BaseHTTP/0.6 Python/3.14.7\r\nDate:  Sun, 15 Nov 2026 10:00:00 GMT \r\n\r\n";
    let (s, e) = raw_header_value(head, "date").unwrap_or((0, 0));
    assert_eq!(head.get(s..e), Some("Sun, 15 Nov 2026 10:00:00 GMT"));
    let twice = "HTTP/1.0 200 OK\r\nDate: a\r\nDate: b\r\n\r\n";
    assert_eq!(raw_header_value(twice, "Date"), None);
    let folded = "HTTP/1.0 200 OK\r\nDate: a\r\n b\r\n\r\n";
    assert_eq!(raw_header_value(folded, "Date"), None);
    // the status line is never a header line
    assert_eq!(raw_header_value("Date: x\r\n\r\n", "Date"), None);
}

#[test]
fn base64_round_trips() {
    for bytes in [&b""[..], b"f", b"fo", b"foo", b"\xff\x00\xfe\x01"] {
        let enc = crate::observe::base64(bytes);
        assert_eq!(base64_decode(&enc).as_deref(), Some(bytes), "{enc}");
    }
    for bad in ["Zg=", "Zg==Zg==", "Z===", "Zm9v!"] {
        assert_eq!(base64_decode(bad), None, "{bad}");
    }
}

#[test]
fn base64_is_bounded_by_what_the_client_can_receive() {
    // the client records up to its wire limit; all of it must decode, so a large
    // non-UTF-8 body is compared as sent instead of failing the comparison
    assert!(MAX_DECODED_BYTES >= crate::client::ReadLimits::default().max_wire_bytes);
    const { assert!(MAX_DECODED_BYTES > MAX_TEXT_BYTES) };
    let enc = crate::observe::base64(&[0xff; 7]);
    assert_eq!(base64_decode_within(&enc, 7).map(|v| v.len()), Some(7));
    assert_eq!(base64_decode_within(&enc, 9).map(|v| v.len()), Some(7));
    assert_eq!(base64_decode_within(&enc, 5), None);
}

#[test]
fn a_file_id_is_probed_with_the_prefix_it_is_numbered_under() {
    let dsi = Pattern::compile("req-<hex12>.dsi").unwrap_or_else(|e| panic!("{e}"));
    assert_eq!(id_hole_prefix(&dsi), "req-");
    let jsonl = Pattern::compile("chatcmpl-<hex24>.jsonl").unwrap_or_else(|e| panic!("{e}"));
    assert_eq!(id_hole_prefix(&jsonl), "chatcmpl-");
}

#[test]
fn id_numbers_are_masked_for_ordering_only() {
    assert_eq!(
        mask_id_numbers("{\"id\": \"<chatcmpl-#12>\", \"n\": \"#3\", \"t\": \"<req-#1>.dsi\"}"),
        "{\"id\": \"<chatcmpl-#>\", \"n\": \"#3\", \"t\": \"<req-#>.dsi\"}"
    );
}

#[test]
fn line_start_search_skips_matches_inside_a_line() {
    let text = ": data: x\n\ndata: x\n\n";
    assert_eq!(find_at_line_start(text, "data: x\n\n", 0), Some(11));
    assert_eq!(find_at_line_start(text, "nothing", 0), None);
}

#[test]
fn plain_json_content() {
    assert!(is_plain_json_content("PULSAR_CONSOLE_X and text"));
    assert!(!is_plain_json_content("a\"b"));
    assert!(!is_plain_json_content("a\\b"));
    assert!(!is_plain_json_content("a\nb"));
}

#[test]
fn pointer_segments_are_escaped() {
    assert_eq!(pointer_segment("a/b~c"), "a~1b~0c");
}
