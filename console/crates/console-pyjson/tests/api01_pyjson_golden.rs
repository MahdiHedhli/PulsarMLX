//! Golden tables for the Python-compatible JSON writer and reader (work package API-01,
//! absorbing PRM-01 and the JSON writer of OPS-01).
//!
//! Every expected string in this file was recorded from CPython 3.14.7 (Unicode 16.0.0), run
//! in isolated mode with the standard library only, as
//! `python3 -I -c 'import json; print(json.dumps(json.loads(SRC), **KWARGS))'`, and likewise
//! with `repr(float)`, `json.JSONDecoder().raw_decode(s, idx)` and `json.loads(bytes)`. No
//! donor file was run to produce them. Each row can be checked against CPython's documented
//! rules: `json.dumps` separators, `ensure_ascii` escaping with surrogate pairs, float `repr`
//! (shortest round-trip digits, exponent form when the decimal exponent is below -4 or at
//! least 16), `indent`, `sort_keys` and `allow_nan`; and the error messages of the C scanner
//! in `Modules/_json.c`.
//!
//! Behavior reference: project-maya serve/server.py:5457-5463, 2577, 2818, 2863, 2918 and
//! serve/models.py:662-700 at 7e68a30f (the `json.dumps` modes the donor writes with).

use console_pyjson::dumps::{
    dumps, dumps_str, float_value, to_file, to_python_default, to_wire, DumpsError, DumpsOptions,
    Indent,
};
use console_pyjson::float_repr::repr_f64;
use console_pyjson::loads::{loads, loads_bytes, raw_decode, LoadsError, INT_MAX_STR_DIGITS};
use serde_json::Value;

fn parse(src: &str) -> Value {
    match loads(src) {
        Ok(v) => v,
        Err(e) => panic!("test input {src:?} does not parse: {e}"),
    }
}

fn wire(v: &Value) -> String {
    to_wire(v).unwrap_or_else(|e| panic!("to_wire failed: {e}"))
}

/// API-01 table: (JSON source, `json.dumps(v, ensure_ascii=False)`, `json.dumps(v)`).
const VALUES: &[(&str, &str, &str)] = &[
    ("null", "null", "null"),
    ("true", "true", "true"),
    ("false", "false", "false"),
    ("0", "0", "0"),
    ("-0", "0", "0"),
    ("1", "1", "1"),
    ("-1", "-1", "-1"),
    (
        "123456789012345678901234567890",
        "123456789012345678901234567890",
        "123456789012345678901234567890",
    ),
    (
        "-98765432109876543210",
        "-98765432109876543210",
        "-98765432109876543210",
    ),
    (
        "18446744073709551616",
        "18446744073709551616",
        "18446744073709551616",
    ),
    (
        "9223372036854775808",
        "9223372036854775808",
        "9223372036854775808",
    ),
    ("0.0", "0.0", "0.0"),
    ("-0.0", "-0.0", "-0.0"),
    ("1.0", "1.0", "1.0"),
    ("2.50", "2.5", "2.5"),
    ("0.1", "0.1", "0.1"),
    ("1e-05", "1e-05", "1e-05"),
    ("0.0001", "0.0001", "0.0001"),
    ("1e16", "1e+16", "1e+16"),
    ("1E16", "1e+16", "1e+16"),
    ("1.5e16", "1.5e+16", "1.5e+16"),
    (
        "9999999999999998.0",
        "9999999999999998.0",
        "9999999999999998.0",
    ),
    ("123456789.0", "123456789.0", "123456789.0"),
    ("5e-324", "5e-324", "5e-324"),
    (
        "1.7976931348623157e308",
        "1.7976931348623157e+308",
        "1.7976931348623157e+308",
    ),
    ("1e400", "Infinity", "Infinity"),
    ("-1e400", "-Infinity", "-Infinity"),
    ("NaN", "NaN", "NaN"),
    ("Infinity", "Infinity", "Infinity"),
    ("-Infinity", "-Infinity", "-Infinity"),
    (
        "0.30000000000000004",
        "0.30000000000000004",
        "0.30000000000000004",
    ),
    ("100", "100", "100"),
    ("1e2", "100.0", "100.0"),
    ("1.25e-7", "1.25e-07", "1.25e-07"),
    ("6.02214076e23", "6.02214076e+23", "6.02214076e+23"),
    (
        "2.2250738585072014e-308",
        "2.2250738585072014e-308",
        "2.2250738585072014e-308",
    ),
    (
        "3.141592653589793",
        "3.141592653589793",
        "3.141592653589793",
    ),
    ("\"\"", "\"\"", "\"\""),
    ("\"plain\"", "\"plain\"", "\"plain\""),
    (
        "\"quote\\\" backslash\\\\ slash\\/\"",
        "\"quote\\\" backslash\\\\ slash/\"",
        "\"quote\\\" backslash\\\\ slash/\"",
    ),
    (
        "\"\\b\\f\\n\\r\\t\"",
        "\"\\b\\f\\n\\r\\t\"",
        "\"\\b\\f\\n\\r\\t\"",
    ),
    (
        "\"\\u0000\\u001f\\u0007\"",
        "\"\\u0000\\u001f\\u0007\"",
        "\"\\u0000\\u001f\\u0007\"",
    ),
    ("\"\\u007f\"", "\"\u{7f}\"", "\"\\u007f\""),
    ("\"caf\u{e9}\"", "\"caf\u{e9}\"", "\"caf\\u00e9\""),
    (
        "\"\u{4e2d}\u{6587}\"",
        "\"\u{4e2d}\u{6587}\"",
        "\"\\u4e2d\\u6587\"",
    ),
    (
        "\"\\ud83d\\ude00 emoji\"",
        "\"\u{1f600} emoji\"",
        "\"\\ud83d\\ude00 emoji\"",
    ),
    ("\"\u{1f600}\"", "\"\u{1f600}\"", "\"\\ud83d\\ude00\""),
    (
        "\"\u{2028}\u{2029}\"",
        "\"\u{2028}\u{2029}\"",
        "\"\\u2028\\u2029\"",
    ),
    (
        "\"<script>&amp;</script>\"",
        "\"<script>&amp;</script>\"",
        "\"<script>&amp;</script>\"",
    ),
    ("\"\u{a0}\u{85}\"", "\"\u{a0}\u{85}\"", "\"\\u00a0\\u0085\""),
    (
        "\"\\uffff\\ufffe\"",
        "\"\u{ffff}\u{fffe}\"",
        "\"\\uffff\\ufffe\"",
    ),
    (
        "\"\u{10000}\u{10ffff}\"",
        "\"\u{10000}\u{10ffff}\"",
        "\"\\ud800\\udc00\\udbff\\udfff\"",
    ),
    ("[]", "[]", "[]"),
    ("{}", "{}", "{}"),
    ("[[]]", "[[]]", "[[]]"),
    ("[{}]", "[{}]", "[{}]"),
    ("{\"a\": {}}", "{\"a\": {}}", "{\"a\": {}}"),
    ("{\"a\": []}", "{\"a\": []}", "{\"a\": []}"),
    ("[1, 2, 3]", "[1, 2, 3]", "[1, 2, 3]"),
    (
        "[1, [2, [3, []]]]",
        "[1, [2, [3, []]]]",
        "[1, [2, [3, []]]]",
    ),
    (
        "{\"b\": 1, \"a\": 2}",
        "{\"b\": 1, \"a\": 2}",
        "{\"b\": 1, \"a\": 2}",
    ),
    (
        "{\"z\": {\"y\": 1, \"x\": [1, {\"w\": null}]}}",
        "{\"z\": {\"y\": 1, \"x\": [1, {\"w\": null}]}}",
        "{\"z\": {\"y\": 1, \"x\": [1, {\"w\": null}]}}",
    ),
    (
        "{\"\u{e9}\": \"\u{e8}\", \"e\": 1}",
        "{\"\u{e9}\": \"\u{e8}\", \"e\": 1}",
        "{\"\\u00e9\": \"\\u00e8\", \"e\": 1}",
    ),
    ("{\"a\": 1, \"a\": 2}", "{\"a\": 2}", "{\"a\": 2}"),
    (
        "{\"k\": [true, false, null, 1.5, \"s\"]}",
        "{\"k\": [true, false, null, 1.5, \"s\"]}",
        "{\"k\": [true, false, null, 1.5, \"s\"]}",
    ),
    ("{\"\": \"\"}", "{\"\": \"\"}", "{\"\": \"\"}"),
    (
        "{\"B\": 1, \"a\": 2, \"_\": 3, \"\u{e9}\": 4, \"\u{1f600}\": 5, \"1\": 6}",
        "{\"B\": 1, \"a\": 2, \"_\": 3, \"\u{e9}\": 4, \"\u{1f600}\": 5, \"1\": 6}",
        "{\"B\": 1, \"a\": 2, \"_\": 3, \"\\u00e9\": 4, \"\\ud83d\\ude00\": 5, \"1\": 6}",
    ),
    (
        "[NaN, Infinity, -Infinity]",
        "[NaN, Infinity, -Infinity]",
        "[NaN, Infinity, -Infinity]",
    ),
    (
        "{\"nested\": {\"empty_list\": [], \"empty_obj\": {}, \"list\": [[], {}]}}",
        "{\"nested\": {\"empty_list\": [], \"empty_obj\": {}, \"list\": [[], {}]}}",
        "{\"nested\": {\"empty_list\": [], \"empty_obj\": {}, \"list\": [[], {}]}}",
    ),
];

#[test]
fn api01_value_table_matches_python() {
    assert!(VALUES.len() >= 40);
    for (src, expected_wire, expected_default) in VALUES {
        let v = parse(src);
        assert_eq!(wire(&v), *expected_wire, "wire form of {src:?}");
        assert_eq!(
            to_python_default(&v).ok().as_deref(),
            Some(*expected_default),
            "default form of {src:?}"
        );
    }
}

fn options(name: &str) -> DumpsOptions {
    match name {
        "default" => DumpsOptions::python_default(),
        "wire" => DumpsOptions::wire(),
        "file" => DumpsOptions::file(),
        "file_utf8" => DumpsOptions::file().ensure_ascii(false),
        "sorted" => DumpsOptions::python_default().sort_keys(true),
        "compact" => DumpsOptions::python_default().separators(",", ":"),
        "indent2_sorted" => DumpsOptions::python_default()
            .indent(Some(Indent::Spaces(2)))
            .sort_keys(true),
        "indent_tab" => DumpsOptions::wire().indent(Some(Indent::Text("\t".into()))),
        "indent0" => DumpsOptions::python_default().indent(Some(Indent::Spaces(0))),
        "indent2_spaced" => DumpsOptions::python_default()
            .indent(Some(Indent::Spaces(2)))
            .separators(", ", ": "),
        other => panic!("unknown option set {other}"),
    }
}

/// PRM-01 table: (option set, JSON source, Python output). Option sets: `file` is
/// `indent=1`; `file_utf8` adds `ensure_ascii=False`; `sorted` is `sort_keys=True`;
/// `compact` is `separators=(",", ":")`; `indent2_sorted` is `indent=2, sort_keys=True`;
/// `indent_tab` is `indent="\t", ensure_ascii=False`; `indent0` is `indent=0`;
/// `indent2_spaced` is `indent=2, separators=(", ", ": ")`.
const PAIRS: &[(&str, &str, &str)] = &[
    ("file", "[]", "[]"),
    ("file", "{}", "{}"),
    ("file", "[[]]", "[\n []\n]"),
    ("file", "[{}]", "[\n {}\n]"),
    ("file", "{\"a\": {}}", "{\n \"a\": {}\n}"),
    ("file", "{\"a\": []}", "{\n \"a\": []\n}"),
    ("file", "[1, 2, 3]", "[\n 1,\n 2,\n 3\n]"),
    ("file", "[1, [2, [3, []]]]", "[\n 1,\n [\n  2,\n  [\n   3,\n   []\n  ]\n ]\n]"),
    ("file", "{\"b\": 1, \"a\": 2}", "{\n \"b\": 1,\n \"a\": 2\n}"),
    ("file", "{\"z\": {\"y\": 1, \"x\": [1, {\"w\": null}]}}", "{\n \"z\": {\n  \"y\": 1,\n  \"x\": [\n   1,\n   {\n    \"w\": null\n   }\n  ]\n }\n}"),
    ("file", "{\"\u{e9}\": \"\u{e8}\", \"e\": 1}", "{\n \"\\u00e9\": \"\\u00e8\",\n \"e\": 1\n}"),
    ("file", "{\"a\": 1, \"a\": 2}", "{\n \"a\": 2\n}"),
    ("file", "{\"k\": [true, false, null, 1.5, \"s\"]}", "{\n \"k\": [\n  true,\n  false,\n  null,\n  1.5,\n  \"s\"\n ]\n}"),
    ("file", "{\"\": \"\"}", "{\n \"\": \"\"\n}"),
    ("file", "{\"B\": 1, \"a\": 2, \"_\": 3, \"\u{e9}\": 4, \"\u{1f600}\": 5, \"1\": 6}", "{\n \"B\": 1,\n \"a\": 2,\n \"_\": 3,\n \"\\u00e9\": 4,\n \"\\ud83d\\ude00\": 5,\n \"1\": 6\n}"),
    ("file", "[NaN, Infinity, -Infinity]", "[\n NaN,\n Infinity,\n -Infinity\n]"),
    ("file", "{\"nested\": {\"empty_list\": [], \"empty_obj\": {}, \"list\": [[], {}]}}", "{\n \"nested\": {\n  \"empty_list\": [],\n  \"empty_obj\": {},\n  \"list\": [\n   [],\n   {}\n  ]\n }\n}"),
    ("file", "\"caf\u{e9} \u{1f600}\"", "\"caf\\u00e9 \\ud83d\\ude00\""),
    ("file", "1e16", "1e+16"),
    ("file", "-0.0", "-0.0"),
    ("file_utf8", "[]", "[]"),
    ("file_utf8", "{}", "{}"),
    ("file_utf8", "[[]]", "[\n []\n]"),
    ("file_utf8", "[{}]", "[\n {}\n]"),
    ("file_utf8", "{\"a\": {}}", "{\n \"a\": {}\n}"),
    ("file_utf8", "{\"a\": []}", "{\n \"a\": []\n}"),
    ("file_utf8", "[1, 2, 3]", "[\n 1,\n 2,\n 3\n]"),
    ("file_utf8", "[1, [2, [3, []]]]", "[\n 1,\n [\n  2,\n  [\n   3,\n   []\n  ]\n ]\n]"),
    ("file_utf8", "{\"b\": 1, \"a\": 2}", "{\n \"b\": 1,\n \"a\": 2\n}"),
    ("file_utf8", "{\"z\": {\"y\": 1, \"x\": [1, {\"w\": null}]}}", "{\n \"z\": {\n  \"y\": 1,\n  \"x\": [\n   1,\n   {\n    \"w\": null\n   }\n  ]\n }\n}"),
    ("file_utf8", "{\"\u{e9}\": \"\u{e8}\", \"e\": 1}", "{\n \"\u{e9}\": \"\u{e8}\",\n \"e\": 1\n}"),
    ("file_utf8", "{\"a\": 1, \"a\": 2}", "{\n \"a\": 2\n}"),
    ("file_utf8", "{\"k\": [true, false, null, 1.5, \"s\"]}", "{\n \"k\": [\n  true,\n  false,\n  null,\n  1.5,\n  \"s\"\n ]\n}"),
    ("file_utf8", "{\"\": \"\"}", "{\n \"\": \"\"\n}"),
    ("file_utf8", "{\"B\": 1, \"a\": 2, \"_\": 3, \"\u{e9}\": 4, \"\u{1f600}\": 5, \"1\": 6}", "{\n \"B\": 1,\n \"a\": 2,\n \"_\": 3,\n \"\u{e9}\": 4,\n \"\u{1f600}\": 5,\n \"1\": 6\n}"),
    ("file_utf8", "[NaN, Infinity, -Infinity]", "[\n NaN,\n Infinity,\n -Infinity\n]"),
    ("file_utf8", "{\"nested\": {\"empty_list\": [], \"empty_obj\": {}, \"list\": [[], {}]}}", "{\n \"nested\": {\n  \"empty_list\": [],\n  \"empty_obj\": {},\n  \"list\": [\n   [],\n   {}\n  ]\n }\n}"),
    ("file_utf8", "\"caf\u{e9} \u{1f600}\"", "\"caf\u{e9} \u{1f600}\""),
    ("file_utf8", "1e16", "1e+16"),
    ("file_utf8", "-0.0", "-0.0"),
    ("sorted", "[]", "[]"),
    ("sorted", "{}", "{}"),
    ("sorted", "[[]]", "[[]]"),
    ("sorted", "[{}]", "[{}]"),
    ("sorted", "{\"a\": {}}", "{\"a\": {}}"),
    ("sorted", "{\"a\": []}", "{\"a\": []}"),
    ("sorted", "[1, 2, 3]", "[1, 2, 3]"),
    ("sorted", "[1, [2, [3, []]]]", "[1, [2, [3, []]]]"),
    ("sorted", "{\"b\": 1, \"a\": 2}", "{\"a\": 2, \"b\": 1}"),
    ("sorted", "{\"z\": {\"y\": 1, \"x\": [1, {\"w\": null}]}}", "{\"z\": {\"x\": [1, {\"w\": null}], \"y\": 1}}"),
    ("sorted", "{\"\u{e9}\": \"\u{e8}\", \"e\": 1}", "{\"e\": 1, \"\\u00e9\": \"\\u00e8\"}"),
    ("sorted", "{\"a\": 1, \"a\": 2}", "{\"a\": 2}"),
    ("sorted", "{\"k\": [true, false, null, 1.5, \"s\"]}", "{\"k\": [true, false, null, 1.5, \"s\"]}"),
    ("sorted", "{\"\": \"\"}", "{\"\": \"\"}"),
    ("sorted", "{\"B\": 1, \"a\": 2, \"_\": 3, \"\u{e9}\": 4, \"\u{1f600}\": 5, \"1\": 6}", "{\"1\": 6, \"B\": 1, \"_\": 3, \"a\": 2, \"\\u00e9\": 4, \"\\ud83d\\ude00\": 5}"),
    ("sorted", "[NaN, Infinity, -Infinity]", "[NaN, Infinity, -Infinity]"),
    ("sorted", "{\"nested\": {\"empty_list\": [], \"empty_obj\": {}, \"list\": [[], {}]}}", "{\"nested\": {\"empty_list\": [], \"empty_obj\": {}, \"list\": [[], {}]}}"),
    ("sorted", "\"caf\u{e9} \u{1f600}\"", "\"caf\\u00e9 \\ud83d\\ude00\""),
    ("sorted", "1e16", "1e+16"),
    ("sorted", "-0.0", "-0.0"),
    ("compact", "[]", "[]"),
    ("compact", "{}", "{}"),
    ("compact", "[[]]", "[[]]"),
    ("compact", "[{}]", "[{}]"),
    ("compact", "{\"a\": {}}", "{\"a\":{}}"),
    ("compact", "{\"a\": []}", "{\"a\":[]}"),
    ("compact", "[1, 2, 3]", "[1,2,3]"),
    ("compact", "[1, [2, [3, []]]]", "[1,[2,[3,[]]]]"),
    ("compact", "{\"b\": 1, \"a\": 2}", "{\"b\":1,\"a\":2}"),
    ("compact", "{\"z\": {\"y\": 1, \"x\": [1, {\"w\": null}]}}", "{\"z\":{\"y\":1,\"x\":[1,{\"w\":null}]}}"),
    ("compact", "{\"\u{e9}\": \"\u{e8}\", \"e\": 1}", "{\"\\u00e9\":\"\\u00e8\",\"e\":1}"),
    ("compact", "{\"a\": 1, \"a\": 2}", "{\"a\":2}"),
    ("compact", "{\"k\": [true, false, null, 1.5, \"s\"]}", "{\"k\":[true,false,null,1.5,\"s\"]}"),
    ("compact", "{\"\": \"\"}", "{\"\":\"\"}"),
    ("compact", "{\"B\": 1, \"a\": 2, \"_\": 3, \"\u{e9}\": 4, \"\u{1f600}\": 5, \"1\": 6}", "{\"B\":1,\"a\":2,\"_\":3,\"\\u00e9\":4,\"\\ud83d\\ude00\":5,\"1\":6}"),
    ("compact", "[NaN, Infinity, -Infinity]", "[NaN,Infinity,-Infinity]"),
    ("compact", "{\"nested\": {\"empty_list\": [], \"empty_obj\": {}, \"list\": [[], {}]}}", "{\"nested\":{\"empty_list\":[],\"empty_obj\":{},\"list\":[[],{}]}}"),
    ("compact", "\"caf\u{e9} \u{1f600}\"", "\"caf\\u00e9 \\ud83d\\ude00\""),
    ("compact", "1e16", "1e+16"),
    ("compact", "-0.0", "-0.0"),
    ("indent2_sorted", "[]", "[]"),
    ("indent2_sorted", "{}", "{}"),
    ("indent2_sorted", "[[]]", "[\n  []\n]"),
    ("indent2_sorted", "[{}]", "[\n  {}\n]"),
    ("indent2_sorted", "{\"a\": {}}", "{\n  \"a\": {}\n}"),
    ("indent2_sorted", "{\"a\": []}", "{\n  \"a\": []\n}"),
    ("indent2_sorted", "[1, 2, 3]", "[\n  1,\n  2,\n  3\n]"),
    ("indent2_sorted", "[1, [2, [3, []]]]", "[\n  1,\n  [\n    2,\n    [\n      3,\n      []\n    ]\n  ]\n]"),
    ("indent2_sorted", "{\"b\": 1, \"a\": 2}", "{\n  \"a\": 2,\n  \"b\": 1\n}"),
    ("indent2_sorted", "{\"z\": {\"y\": 1, \"x\": [1, {\"w\": null}]}}", "{\n  \"z\": {\n    \"x\": [\n      1,\n      {\n        \"w\": null\n      }\n    ],\n    \"y\": 1\n  }\n}"),
    ("indent2_sorted", "{\"\u{e9}\": \"\u{e8}\", \"e\": 1}", "{\n  \"e\": 1,\n  \"\\u00e9\": \"\\u00e8\"\n}"),
    ("indent2_sorted", "{\"a\": 1, \"a\": 2}", "{\n  \"a\": 2\n}"),
    ("indent2_sorted", "{\"k\": [true, false, null, 1.5, \"s\"]}", "{\n  \"k\": [\n    true,\n    false,\n    null,\n    1.5,\n    \"s\"\n  ]\n}"),
    ("indent2_sorted", "{\"\": \"\"}", "{\n  \"\": \"\"\n}"),
    ("indent2_sorted", "{\"B\": 1, \"a\": 2, \"_\": 3, \"\u{e9}\": 4, \"\u{1f600}\": 5, \"1\": 6}", "{\n  \"1\": 6,\n  \"B\": 1,\n  \"_\": 3,\n  \"a\": 2,\n  \"\\u00e9\": 4,\n  \"\\ud83d\\ude00\": 5\n}"),
    ("indent2_sorted", "[NaN, Infinity, -Infinity]", "[\n  NaN,\n  Infinity,\n  -Infinity\n]"),
    ("indent2_sorted", "{\"nested\": {\"empty_list\": [], \"empty_obj\": {}, \"list\": [[], {}]}}", "{\n  \"nested\": {\n    \"empty_list\": [],\n    \"empty_obj\": {},\n    \"list\": [\n      [],\n      {}\n    ]\n  }\n}"),
    ("indent2_sorted", "\"caf\u{e9} \u{1f600}\"", "\"caf\\u00e9 \\ud83d\\ude00\""),
    ("indent2_sorted", "1e16", "1e+16"),
    ("indent2_sorted", "-0.0", "-0.0"),
    ("indent_tab", "[]", "[]"),
    ("indent_tab", "{}", "{}"),
    ("indent_tab", "[[]]", "[\n\t[]\n]"),
    ("indent_tab", "[{}]", "[\n\t{}\n]"),
    ("indent_tab", "{\"a\": {}}", "{\n\t\"a\": {}\n}"),
    ("indent_tab", "{\"a\": []}", "{\n\t\"a\": []\n}"),
    ("indent_tab", "[1, 2, 3]", "[\n\t1,\n\t2,\n\t3\n]"),
    ("indent_tab", "[1, [2, [3, []]]]", "[\n\t1,\n\t[\n\t\t2,\n\t\t[\n\t\t\t3,\n\t\t\t[]\n\t\t]\n\t]\n]"),
    ("indent_tab", "{\"b\": 1, \"a\": 2}", "{\n\t\"b\": 1,\n\t\"a\": 2\n}"),
    ("indent_tab", "{\"z\": {\"y\": 1, \"x\": [1, {\"w\": null}]}}", "{\n\t\"z\": {\n\t\t\"y\": 1,\n\t\t\"x\": [\n\t\t\t1,\n\t\t\t{\n\t\t\t\t\"w\": null\n\t\t\t}\n\t\t]\n\t}\n}"),
    ("indent_tab", "{\"\u{e9}\": \"\u{e8}\", \"e\": 1}", "{\n\t\"\u{e9}\": \"\u{e8}\",\n\t\"e\": 1\n}"),
    ("indent_tab", "{\"a\": 1, \"a\": 2}", "{\n\t\"a\": 2\n}"),
    ("indent_tab", "{\"k\": [true, false, null, 1.5, \"s\"]}", "{\n\t\"k\": [\n\t\ttrue,\n\t\tfalse,\n\t\tnull,\n\t\t1.5,\n\t\t\"s\"\n\t]\n}"),
    ("indent_tab", "{\"\": \"\"}", "{\n\t\"\": \"\"\n}"),
    ("indent_tab", "{\"B\": 1, \"a\": 2, \"_\": 3, \"\u{e9}\": 4, \"\u{1f600}\": 5, \"1\": 6}", "{\n\t\"B\": 1,\n\t\"a\": 2,\n\t\"_\": 3,\n\t\"\u{e9}\": 4,\n\t\"\u{1f600}\": 5,\n\t\"1\": 6\n}"),
    ("indent_tab", "[NaN, Infinity, -Infinity]", "[\n\tNaN,\n\tInfinity,\n\t-Infinity\n]"),
    ("indent_tab", "{\"nested\": {\"empty_list\": [], \"empty_obj\": {}, \"list\": [[], {}]}}", "{\n\t\"nested\": {\n\t\t\"empty_list\": [],\n\t\t\"empty_obj\": {},\n\t\t\"list\": [\n\t\t\t[],\n\t\t\t{}\n\t\t]\n\t}\n}"),
    ("indent_tab", "\"caf\u{e9} \u{1f600}\"", "\"caf\u{e9} \u{1f600}\""),
    ("indent_tab", "1e16", "1e+16"),
    ("indent_tab", "-0.0", "-0.0"),
    ("indent0", "[]", "[]"),
    ("indent0", "{}", "{}"),
    ("indent0", "[[]]", "[\n[]\n]"),
    ("indent0", "[{}]", "[\n{}\n]"),
    ("indent0", "{\"a\": {}}", "{\n\"a\": {}\n}"),
    ("indent0", "{\"a\": []}", "{\n\"a\": []\n}"),
    ("indent0", "[1, 2, 3]", "[\n1,\n2,\n3\n]"),
    ("indent0", "[1, [2, [3, []]]]", "[\n1,\n[\n2,\n[\n3,\n[]\n]\n]\n]"),
    ("indent0", "{\"b\": 1, \"a\": 2}", "{\n\"b\": 1,\n\"a\": 2\n}"),
    ("indent0", "{\"z\": {\"y\": 1, \"x\": [1, {\"w\": null}]}}", "{\n\"z\": {\n\"y\": 1,\n\"x\": [\n1,\n{\n\"w\": null\n}\n]\n}\n}"),
    ("indent0", "{\"\u{e9}\": \"\u{e8}\", \"e\": 1}", "{\n\"\\u00e9\": \"\\u00e8\",\n\"e\": 1\n}"),
    ("indent0", "{\"a\": 1, \"a\": 2}", "{\n\"a\": 2\n}"),
    ("indent0", "{\"k\": [true, false, null, 1.5, \"s\"]}", "{\n\"k\": [\ntrue,\nfalse,\nnull,\n1.5,\n\"s\"\n]\n}"),
    ("indent0", "{\"\": \"\"}", "{\n\"\": \"\"\n}"),
    ("indent0", "{\"B\": 1, \"a\": 2, \"_\": 3, \"\u{e9}\": 4, \"\u{1f600}\": 5, \"1\": 6}", "{\n\"B\": 1,\n\"a\": 2,\n\"_\": 3,\n\"\\u00e9\": 4,\n\"\\ud83d\\ude00\": 5,\n\"1\": 6\n}"),
    ("indent0", "[NaN, Infinity, -Infinity]", "[\nNaN,\nInfinity,\n-Infinity\n]"),
    ("indent0", "{\"nested\": {\"empty_list\": [], \"empty_obj\": {}, \"list\": [[], {}]}}", "{\n\"nested\": {\n\"empty_list\": [],\n\"empty_obj\": {},\n\"list\": [\n[],\n{}\n]\n}\n}"),
    ("indent0", "\"caf\u{e9} \u{1f600}\"", "\"caf\\u00e9 \\ud83d\\ude00\""),
    ("indent0", "1e16", "1e+16"),
    ("indent0", "-0.0", "-0.0"),
    ("indent2_spaced", "[]", "[]"),
    ("indent2_spaced", "{}", "{}"),
    ("indent2_spaced", "[[]]", "[\n  []\n]"),
    ("indent2_spaced", "[{}]", "[\n  {}\n]"),
    ("indent2_spaced", "{\"a\": {}}", "{\n  \"a\": {}\n}"),
    ("indent2_spaced", "{\"a\": []}", "{\n  \"a\": []\n}"),
    ("indent2_spaced", "[1, 2, 3]", "[\n  1, \n  2, \n  3\n]"),
    ("indent2_spaced", "[1, [2, [3, []]]]", "[\n  1, \n  [\n    2, \n    [\n      3, \n      []\n    ]\n  ]\n]"),
    ("indent2_spaced", "{\"b\": 1, \"a\": 2}", "{\n  \"b\": 1, \n  \"a\": 2\n}"),
    ("indent2_spaced", "{\"z\": {\"y\": 1, \"x\": [1, {\"w\": null}]}}", "{\n  \"z\": {\n    \"y\": 1, \n    \"x\": [\n      1, \n      {\n        \"w\": null\n      }\n    ]\n  }\n}"),
    ("indent2_spaced", "{\"\u{e9}\": \"\u{e8}\", \"e\": 1}", "{\n  \"\\u00e9\": \"\\u00e8\", \n  \"e\": 1\n}"),
    ("indent2_spaced", "{\"a\": 1, \"a\": 2}", "{\n  \"a\": 2\n}"),
    ("indent2_spaced", "{\"k\": [true, false, null, 1.5, \"s\"]}", "{\n  \"k\": [\n    true, \n    false, \n    null, \n    1.5, \n    \"s\"\n  ]\n}"),
    ("indent2_spaced", "{\"\": \"\"}", "{\n  \"\": \"\"\n}"),
    ("indent2_spaced", "{\"B\": 1, \"a\": 2, \"_\": 3, \"\u{e9}\": 4, \"\u{1f600}\": 5, \"1\": 6}", "{\n  \"B\": 1, \n  \"a\": 2, \n  \"_\": 3, \n  \"\\u00e9\": 4, \n  \"\\ud83d\\ude00\": 5, \n  \"1\": 6\n}"),
    ("indent2_spaced", "[NaN, Infinity, -Infinity]", "[\n  NaN, \n  Infinity, \n  -Infinity\n]"),
    ("indent2_spaced", "{\"nested\": {\"empty_list\": [], \"empty_obj\": {}, \"list\": [[], {}]}}", "{\n  \"nested\": {\n    \"empty_list\": [], \n    \"empty_obj\": {}, \n    \"list\": [\n      [], \n      {}\n    ]\n  }\n}"),
    ("indent2_spaced", "\"caf\u{e9} \u{1f600}\"", "\"caf\\u00e9 \\ud83d\\ude00\""),
    ("indent2_spaced", "1e16", "1e+16"),
    ("indent2_spaced", "-0.0", "-0.0"),
];

#[test]
fn prm01_option_pairs_match_python() {
    assert!(PAIRS.len() >= 120);
    for (name, src, expected) in PAIRS {
        let v = parse(src);
        assert_eq!(
            dumps(&v, &options(name)).ok().as_deref(),
            Some(*expected),
            "{name} form of {src:?}"
        );
    }
}

/// `repr(float)`.
const FLOATS: &[(f64, &str)] = &[
    (0.0, "0.0"),
    (-0.0, "-0.0"),
    (1.0, "1.0"),
    (-1.0, "-1.0"),
    (0.1, "0.1"),
    (0.2, "0.2"),
    (0.30000000000000004, "0.30000000000000004"),
    (0.3333333333333333, "0.3333333333333333"),
    (0.6666666666666666, "0.6666666666666666"),
    (0.0001, "0.0001"),
    (1e-05, "1e-05"),
    (1.5e-05, "1.5e-05"),
    (9.999999999999999e-05, "9.999999999999999e-05"),
    (1000000000000000.0, "1000000000000000.0"),
    (1e+16, "1e+16"),
    (1e+17, "1e+17"),
    (9999999999999998.0, "9999999999999998.0"),
    (1e+16, "1e+16"),
    (1.2345678901234568e+16, "1.2345678901234568e+16"),
    (123456789.0, "123456789.0"),
    (1e+22, "1e+22"),
    (1e+23, "1e+23"),
    (1.7976931348623157e+308, "1.7976931348623157e+308"),
    (5e-324, "5e-324"),
    (1e-323, "1e-323"),
    (2.2250738585072014e-308, "2.2250738585072014e-308"),
    (2.225073858507201e-308, "2.225073858507201e-308"),
    (4.35, "4.35"),
    (0.5, "0.5"),
    (100.0, "100.0"),
    (1e+100, "1e+100"),
    (1e-100, "1e-100"),
    (3.14158, "3.14158"),
    (std::f64::consts::E, "2.718281828459045"),
    (6.02214076e+23, "6.02214076e+23"),
    (1.6e-19, "1.6e-19"),
    (299792458.0, "299792458.0"),
    (0.001, "0.001"),
    (123.456, "123.456"),
    (-9.87654e-10, "-9.87654e-10"),
    (1e+21, "1e+21"),
    (1e-07, "1e-07"),
    (5e-324, "5e-324"),
    (8.98846567431158e+307, "8.98846567431158e+307"),
    (0.7999999999999999, "0.7999999999999999"),
    (1.2100000000000002, "1.2100000000000002"),
];

#[test]
fn float_repr_table_matches_python() {
    assert!(FLOATS.len() >= 40);
    for (x, expected) in FLOATS {
        assert_eq!(repr_f64(*x), *expected, "repr of {x:e}");
        assert_eq!(wire(&float_value(*x)), *expected, "json of {x:e}");
    }
}

#[test]
fn floats_built_in_code_print_as_python() {
    // serde_json's own `From<f64>` writes `1e16` and `2.0`; the writer renormalizes them.
    let v = serde_json::json!([2.0, 1e16, 0.1, 1e-7, 100.0, -0.0, 12345678.9]);
    assert_eq!(
        wire(&v),
        "[2.0, 1e+16, 0.1, 1e-07, 100.0, -0.0, 12345678.9]"
    );
    let n = serde_json::json!({"n": 7, "m": -3, "u": 18446744073709551615u64});
    assert_eq!(
        wire(&n),
        "{\"n\": 7, \"m\": -3, \"u\": 18446744073709551615}"
    );
}

/// OPS-01 table: (document, `json.dumps(doc, indent=1)`).
const FILE_DOCUMENTS: &[(&str, &str)] = &[
    ("{}", "{}"),
    ("{\"exe\": \"engine\", \"args\": [\"--port\", \"8081\"]}", "{\n \"exe\": \"engine\",\n \"args\": [\n  \"--port\",\n  \"8081\"\n ]\n}"),
    ("{\"exe\": \"engine\", \"args\": [], \"env\": {}}", "{\n \"exe\": \"engine\",\n \"args\": [],\n \"env\": {}\n}"),
    ("{\"port\": 8080, \"host\": \"127.0.0.1\"}", "{\n \"port\": 8080,\n \"host\": \"127.0.0.1\"\n}"),
    ("{\"name\": \"caf\u{e9}\", \"note\": \"\u{4e2d}\u{6587}\"}", "{\n \"name\": \"caf\\u00e9\",\n \"note\": \"\\u4e2d\\u6587\"\n}"),
    ("{\"emoji\": \"\u{1f600}\", \"astral\": \"\u{10348}\"}", "{\n \"emoji\": \"\\ud83d\\ude00\",\n \"astral\": \"\\ud800\\udf48\"\n}"),
    ("{\"sampling\": {\"temperature\": 0.7, \"top_p\": 0.95, \"top_k\": 40, \"min_p\": 0.0}}", "{\n \"sampling\": {\n  \"temperature\": 0.7,\n  \"top_p\": 0.95,\n  \"top_k\": 40,\n  \"min_p\": 0.0\n }\n}"),
    ("{\"sampling\": {\"temperature\": 1.0, \"repeat_penalty\": 1.1}}", "{\n \"sampling\": {\n  \"temperature\": 1.0,\n  \"repeat_penalty\": 1.1\n }\n}"),
    ("{\"thinking_budget\": 0, \"installer\": {\"thinking_budget_set\": true}}", "{\n \"thinking_budget\": 0,\n \"installer\": {\n  \"thinking_budget_set\": true\n }\n}"),
    ("{\"gpu\": [0, 1], \"backend\": \"cuda\"}", "{\n \"gpu\": [\n  0,\n  1\n ],\n \"backend\": \"cuda\"\n}"),
    ("{\"gpu\": \"0,1\"}", "{\n \"gpu\": \"0,1\"\n}"),
    ("{\"gpu\": 2}", "{\n \"gpu\": 2\n}"),
    ("{\"ratio\": 1e-05, \"big\": 1e+16, \"small\": 0.0001}", "{\n \"ratio\": 1e-05,\n \"big\": 1e+16,\n \"small\": 0.0001\n}"),
    ("{\"neg_zero\": -0.0, \"int_zero\": 0, \"float_one\": 1.0}", "{\n \"neg_zero\": -0.0,\n \"int_zero\": 0,\n \"float_one\": 1.0\n}"),
    ("{\"huge\": 123456789012345678901234567890}", "{\n \"huge\": 123456789012345678901234567890\n}"),
    ("{\"nested\": {\"a\": {\"b\": {\"c\": {}}}}}", "{\n \"nested\": {\n  \"a\": {\n   \"b\": {\n    \"c\": {}\n   }\n  }\n }\n}"),
    ("{\"lists\": [[], [[]], [{}]]}", "{\n \"lists\": [\n  [],\n  [\n   []\n  ],\n  [\n   {}\n  ]\n ]\n}"),
    ("{\"mixed\": [1, \"two\", 3.0, null, true, false]}", "{\n \"mixed\": [\n  1,\n  \"two\",\n  3.0,\n  null,\n  true,\n  false\n ]\n}"),
    ("{\"vision\": null, \"vision_off\": false}", "{\n \"vision\": null,\n \"vision_off\": false\n}"),
    ("{\"turbo\": {\"draft\": \"small\", \"n\": 4}}", "{\n \"turbo\": {\n  \"draft\": \"small\",\n  \"n\": 4\n }\n}"),
    ("{\"model_management\": true, \"api_key\": \"k1\"}", "{\n \"model_management\": true,\n \"api_key\": \"k1\"\n}"),
    ("{\"api_key\": [\"k1\", \"k2\"]}", "{\n \"api_key\": [\n  \"k1\",\n  \"k2\"\n ]\n}"),
    ("{\"cors_origins\": [\"http://localhost:3000\"]}", "{\n \"cors_origins\": [\n  \"http://localhost:3000\"\n ]\n}"),
    ("{\"control\": \"\\u0001\\u001f\", \"tab\": \"a\\tb\", \"nl\": \"a\\nb\"}", "{\n \"control\": \"\\u0001\\u001f\",\n \"tab\": \"a\\tb\",\n \"nl\": \"a\\nb\"\n}"),
    ("{\"quote\": \"say \\\"hi\\\"\", \"backslash\": \"C:\\\\path\"}", "{\n \"quote\": \"say \\\"hi\\\"\",\n \"backslash\": \"C:\\\\path\"\n}"),
    ("{\"del\": \"\u{7f}\", \"nbsp\": \"\u{a0}\"}", "{\n \"del\": \"\\u007f\",\n \"nbsp\": \"\\u00a0\"\n}"),
    ("{\"line_sep\": \"\u{2028}\", \"para_sep\": \"\u{2029}\"}", "{\n \"line_sep\": \"\\u2028\",\n \"para_sep\": \"\\u2029\"\n}"),
    ("{\"unknown_key_z\": 1, \"unknown_key_a\": 2, \"exe\": \"e\"}", "{\n \"unknown_key_z\": 1,\n \"unknown_key_a\": 2,\n \"exe\": \"e\"\n}"),
    ("{\"args\": [\"--max-context\", \"131072\", \"--threads\", \"8\"]}", "{\n \"args\": [\n  \"--max-context\",\n  \"131072\",\n  \"--threads\",\n  \"8\"\n ]\n}"),
    ("{\"pi\": 3.141592653589793, \"e\": 2.718281828459045}", "{\n \"pi\": 3.141592653589793,\n \"e\": 2.718281828459045\n}"),
    ("{\"third\": 0.3333333333333333}", "{\n \"third\": 0.3333333333333333\n}"),
    ("{\"float_list\": [0.1, 0.2, 0.30000000000000004]}", "{\n \"float_list\": [\n  0.1,\n  0.2,\n  0.30000000000000004\n ]\n}"),
    ("{\"exp\": [1e+22, 1e-07, 5e-324]}", "{\n \"exp\": [\n  1e+22,\n  1e-07,\n  5e-324\n ]\n}"),
    ("{\"env\": {\"ENGINE_FLAG\": \"1\", \"OTHER\": \"x y\"}}", "{\n \"env\": {\n  \"ENGINE_FLAG\": \"1\",\n  \"OTHER\": \"x y\"\n }\n}"),
    ("{\"empty_string\": \"\", \"space\": \" \"}", "{\n \"empty_string\": \"\",\n \"space\": \" \"\n}"),
    ("{\"deep\": [[[[[1]]]]]}", "{\n \"deep\": [\n  [\n   [\n    [\n     [\n      1\n     ]\n    ]\n   ]\n  ]\n ]\n}"),
    ("{\"unicode_key_\u{e9}\": \"v\"}", "{\n \"unicode_key_\\u00e9\": \"v\"\n}"),
    ("{\"\u{1f600}\": \"astral key\"}", "{\n \"\\ud83d\\ude00\": \"astral key\"\n}"),
    ("{\"ordering\": {\"b\": 1, \"a\": 2, \"c\": {\"z\": 0, \"y\": [1, 2]}}}", "{\n \"ordering\": {\n  \"b\": 1,\n  \"a\": 2,\n  \"c\": {\n   \"z\": 0,\n   \"y\": [\n    1,\n    2\n   ]\n  }\n }\n}"),
    ("{\"max_context\": 32768, \"context_tested\": [4096, 8192, 32768], \"fit\": 0.85}", "{\n \"max_context\": 32768,\n \"context_tested\": [\n  4096,\n  8192,\n  32768\n ],\n \"fit\": 0.85\n}"),
    ("[1, 2]", "[\n 1,\n 2\n]"),
    ("\"just a string\"", "\"just a string\""),
];

#[test]
fn ops01_indent1_documents_match_python_and_round_trip() {
    assert!(FILE_DOCUMENTS.len() >= 40);
    for (src, expected) in FILE_DOCUMENTS {
        let v = parse(src);
        assert_eq!(
            to_file(&v).ok().as_deref(),
            Some(*expected),
            "indent=1 form of {src:?}"
        );
        // A written file read back and written again is byte-identical.
        let again = parse(expected);
        assert_eq!(
            to_file(&again).ok().as_deref(),
            Some(*expected),
            "round trip of {src:?}"
        );
        assert_eq!(again, v, "same value after a round trip of {src:?}");
    }
}

#[test]
fn sort_keys_with_indent_orders_every_level() {
    let v = parse(r#"{"z":[1,{"b":2,"a":[]}],"a":null}"#);
    let opts = DumpsOptions::file().sort_keys(true);
    assert_eq!(
        dumps(&v, &opts).ok().as_deref(),
        Some("{\n \"a\": null,\n \"z\": [\n  1,\n  {\n   \"a\": [],\n   \"b\": 2\n  }\n ]\n}")
    );
    // Insertion order is kept without sort_keys, including after a duplicate key.
    let dup = parse(r#"{"b": 1, "a": 2, "b": 3}"#);
    assert_eq!(wire(&dup), r#"{"b": 3, "a": 2}"#);
}

#[test]
fn string_escapes_match_python() {
    // frontend.py slices json.dumps(s)[1:-1] to build tool-call argument text.
    let s = "a<b\u{2028}\u{1f600}\u{0}\u{7f}";
    assert_eq!(
        dumps_str(s, true),
        "\"a<b\\u2028\\ud83d\\ude00\\u0000\\u007f\""
    );
    assert_eq!(dumps_str(s, false), "\"a<b\u{2028}\u{1f600}\\u0000\u{7f}\"");
}

#[test]
fn allow_nan_false_raises_pythons_value_error() {
    let opts = DumpsOptions::python_default().allow_nan(false);
    for (src, msg) in [
        (
            "NaN",
            "Out of range float values are not JSON compliant: nan",
        ),
        (
            "[Infinity]",
            "Out of range float values are not JSON compliant: inf",
        ),
        (
            "{\"a\": [-Infinity]}",
            "Out of range float values are not JSON compliant: -inf",
        ),
    ] {
        let err = dumps(&parse(src), &opts).err();
        assert_eq!(
            err.as_ref().map(ToString::to_string).as_deref(),
            Some(msg),
            "{src}"
        );
        assert_eq!(err.map(|e| e.python_type()), Some("ValueError"));
    }
    // The Responses store encoding refuses them too.
    assert!(matches!(
        dumps(&parse("[NaN]"), &DumpsOptions::canonical()),
        Err(DumpsError::OutOfRangeFloat(_))
    ));
    assert_eq!(
        dumps(
            &parse(r#"{"b": [1.0, "\u00e9"], "a": 2}"#),
            &DumpsOptions::canonical()
        )
        .ok()
        .as_deref(),
        Some("{\"a\":2,\"b\":[1.0,\"\u{e9}\"]}")
    );
}

#[test]
fn integer_digit_limit_matches_python() {
    let at_limit = "7".repeat(INT_MAX_STR_DIGITS);
    let v = parse(&at_limit);
    assert_eq!(wire(&v), at_limit);
    let over = format!("-{}", "1".repeat(INT_MAX_STR_DIGITS + 1));
    let err = loads(&over).err();
    assert_eq!(err, Some(LoadsError::IntTooLong { digits: 4301 }));
    assert_eq!(
        err.map(|e| e.to_string()).unwrap_or_default(),
        "Exceeds the limit (4300 digits) for integer string conversion: value has 4301 digits; \
         use sys.set_int_max_str_digits() to increase the limit"
    );
    assert_eq!(
        DumpsError::IntTooLong.to_string(),
        "Exceeds the limit (4300 digits) for integer string conversion; \
         use sys.set_int_max_str_digits() to increase the limit"
    );
}

fn loads_outcome(result: Result<Value, LoadsError>) -> String {
    match result {
        Ok(v) => format!("OK {}", wire(&v)),
        Err(e) => format!("{}: {e}", e.python_type()),
    }
}

/// `json.loads(str)`: (input, `OK <json.dumps(v, ensure_ascii=False)>` or the error).
const LOADS: &[(&str, &str)] = &[
    ("", "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"),
    (" ", "JSONDecodeError: Expecting value: line 1 column 2 (char 1)"),
    ("[", "JSONDecodeError: Expecting value: line 1 column 2 (char 1)"),
    ("[1,", "JSONDecodeError: Expecting value: line 1 column 4 (char 3)"),
    ("[1,]", "JSONDecodeError: Illegal trailing comma before end of array: line 1 column 3 (char 2)"),
    ("{\"a\":1,}", "JSONDecodeError: Illegal trailing comma before end of object: line 1 column 7 (char 6)"),
    ("{", "JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)"),
    ("{\"a\"", "JSONDecodeError: Expecting ':' delimiter: line 1 column 5 (char 4)"),
    ("{\"a\" 1}", "JSONDecodeError: Expecting ':' delimiter: line 1 column 6 (char 5)"),
    ("{\"a\":}", "JSONDecodeError: Expecting value: line 1 column 6 (char 5)"),
    ("{1:2}", "JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)"),
    ("[1 2]", "JSONDecodeError: Expecting ',' delimiter: line 1 column 4 (char 3)"),
    ("{\"a\":1 \"b\":2}", "JSONDecodeError: Expecting ',' delimiter: line 1 column 8 (char 7)"),
    ("\"abc", "JSONDecodeError: Unterminated string starting at: line 1 column 1 (char 0)"),
    ("\"a\\x\"", "JSONDecodeError: Invalid \\escape: line 1 column 3 (char 2)"),
    ("\"a\\u12\"", "JSONDecodeError: Invalid \\uXXXX escape: line 1 column 4 (char 3)"),
    ("\"a\\u12g4\"", "JSONDecodeError: Invalid \\uXXXX escape: line 1 column 4 (char 3)"),
    ("\"a\nb\"", "JSONDecodeError: Invalid control character at: line 1 column 3 (char 2)"),
    ("01", "JSONDecodeError: Extra data: line 1 column 2 (char 1)"),
    ("1.", "JSONDecodeError: Extra data: line 1 column 2 (char 1)"),
    ("1e", "JSONDecodeError: Extra data: line 1 column 2 (char 1)"),
    ("1e+", "JSONDecodeError: Extra data: line 1 column 2 (char 1)"),
    ("1.0e+", "JSONDecodeError: Extra data: line 1 column 4 (char 3)"),
    ("-", "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"),
    ("-a", "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"),
    ("nul", "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"),
    ("tru", "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"),
    ("fals", "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"),
    ("-NaN", "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"),
    ("nan", "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"),
    ("inf", "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"),
    ("1 2", "JSONDecodeError: Extra data: line 1 column 3 (char 2)"),
    ("[1]x", "JSONDecodeError: Extra data: line 1 column 4 (char 3)"),
    ("\"\\", "JSONDecodeError: Unterminated string starting at: line 1 column 1 (char 0)"),
    ("\"\\u", "JSONDecodeError: Invalid \\uXXXX escape: line 1 column 3 (char 2)"),
    ("\"\\u1234", "JSONDecodeError: Unterminated string starting at: line 1 column 1 (char 0)"),
    ("\"\\ud83d\\ude00", "JSONDecodeError: Unterminated string starting at: line 1 column 1 (char 0)"),
    ("\"\\ud83d\\u12x4\"", "JSONDecodeError: Invalid \\uXXXX escape: line 1 column 9 (char 8)"),
    ("\"\\ud83d\\ude0", "JSONDecodeError: Invalid \\uXXXX escape: line 1 column 9 (char 8)"),
    ("\u{feff}[]", "JSONDecodeError: Unexpected UTF-8 BOM (decode using utf-8-sig): line 1 column 1 (char 0)"),
    ("[\"a\" ,]", "JSONDecodeError: Illegal trailing comma before end of array: line 1 column 6 (char 5)"),
    ("[,]", "JSONDecodeError: Expecting value: line 1 column 2 (char 1)"),
    ("{,}", "JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)"),
    ("\n\n  x", "JSONDecodeError: Expecting value: line 3 column 3 (char 4)"),
    ("[\n1,\n]", "JSONDecodeError: Illegal trailing comma before end of array: line 2 column 2 (char 3)"),
    ("{\"a\":1,", "JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 8 (char 7)"),
    ("[1, ", "JSONDecodeError: Expecting value: line 1 column 5 (char 4)"),
    ("{\"a\":1, }", "JSONDecodeError: Illegal trailing comma before end of object: line 1 column 7 (char 6)"),
    ("[1,2", "JSONDecodeError: Expecting ',' delimiter: line 1 column 5 (char 4)"),
    ("{\"a\":1", "JSONDecodeError: Expecting ',' delimiter: line 1 column 7 (char 6)"),
    ("\"\t\"", "JSONDecodeError: Invalid control character at: line 1 column 2 (char 1)"),
    ("{\"a\" : 1 , }", "JSONDecodeError: Illegal trailing comma before end of object: line 1 column 10 (char 9)"),
    ("[1,\r\n]", "JSONDecodeError: Illegal trailing comma before end of array: line 1 column 3 (char 2)"),
    ("\"\u{e9}\u{4e2d}\\q\"", "JSONDecodeError: Invalid \\escape: line 1 column 4 (char 3)"),
    ("[\"\u{1f600}\", x]", "JSONDecodeError: Expecting value: line 1 column 7 (char 6)"),
    ("\"\\u00e9\\uD83D\\uDE00\"", "OK \"\u{e9}\u{1f600}\""),
    ("{\"a\":1}\u{a0}", "JSONDecodeError: Extra data: line 1 column 8 (char 7)"),
    ("+1", "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"),
    (".5", "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"),
    ("0x10", "JSONDecodeError: Extra data: line 1 column 2 (char 1)"),
    ("[1,,2]", "JSONDecodeError: Expecting value: line 1 column 4 (char 3)"),
    ("{\"a\":1,,}", "JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 8 (char 7)"),
    ("\"\u{7f}\u{80}\"", "OK \"\u{7f}\u{80}\""),
    ("true false", "JSONDecodeError: Extra data: line 1 column 6 (char 5)"),
    ("[true,false,null,NaN,Infinity,-Infinity]", "OK [true, false, null, NaN, Infinity, -Infinity]"),
    ("  {\"a\" :\t[ 1 ,2 ] }  ", "OK {\"a\": [1, 2]}"),
    ("-0", "OK 0"),
    ("-0.0", "OK -0.0"),
    ("1E400", "OK Infinity"),
    ("-1e400", "OK -Infinity"),
    ("1.5e-7", "OK 1.5e-07"),
    ("0.10000000000000001", "OK 0.1"),
    ("123456789012345678901234567890", "OK 123456789012345678901234567890"),
    ("{\"a\":1,\"a\":2,\"b\":3}", "OK {\"a\": 2, \"b\": 3}"),
    ("\"\\/\"", "OK \"/\""),
    ("[]]", "JSONDecodeError: Extra data: line 1 column 3 (char 2)"),
    ("{}}", "JSONDecodeError: Extra data: line 1 column 3 (char 2)"),
    ("{\"a\":[}", "JSONDecodeError: Expecting value: line 1 column 7 (char 6)"),
    ("[{]", "JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 3 (char 2)"),
    ("\"a\" \"b\"", "JSONDecodeError: Extra data: line 1 column 5 (char 4)"),
    ("\r\n\t 7 \r\n\t", "OK 7"),
];

#[test]
fn loads_table_matches_python() {
    for (src, expected) in LOADS {
        assert_eq!(loads_outcome(loads(src)), *expected, "json.loads({src:?})");
    }
}

/// `json.loads(bytes)`: encoding detection, `surrogatepass` decoding and its errors.
const LOADS_BYTES: &[(&[u8], &str)] = &[
    (b"\xff", "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0: invalid start byte"),
    (b"\x5b\x22\xe2\x82", "UnicodeDecodeError: 'utf-8' codec can't decode bytes in position 2-3: unexpected end of data"),
    (b"\xe2\x28\xa1", "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe2 in position 0: invalid continuation byte"),
    (b"\xe0\xa0\x28", "UnicodeDecodeError: 'utf-8' codec can't decode bytes in position 0-1: invalid continuation byte"),
    (b"\xf0\x90\x80", "UnicodeDecodeError: 'utf-8' codec can't decode bytes in position 0-2: unexpected end of data"),
    (b"\xf0\x90\x80\x28", "UnicodeDecodeError: 'utf-8' codec can't decode bytes in position 0-2: invalid continuation byte"),
    (b"\xc0\x80", "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xc0 in position 0: invalid start byte"),
    (b"\xed\xa0\x80", "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"),
    (b"\xed\xa0\x41", "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xed in position 0: invalid continuation byte"),
    (b"\xef\xbb\xbf\x5b\x31\x2c\x20\xff\x5d", "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 4: invalid start byte"),
    (b"\xef\xbb\xbf\x5b\x31\x5d", "OK [1]"),
    (b"\xff\xfe\x5b\x00\x5d\x00", "OK []"),
    (b"\xff\xfe\x5b\x00\x5d", "UnicodeDecodeError: 'utf-16-le' codec can't decode byte 0x5d in position 4: truncated data"),
    (b"\x5b\x00\x5d", "JSONDecodeError: Expecting value: line 1 column 2 (char 1)"),
    (b"\x5b\x00\x5d\x00\x00", "UnicodeDecodeError: 'utf-16-le' codec can't decode byte 0x00 in position 4: truncated data"),
    (b"\xfe\xff\x00\x5b\x00\x5d", "OK []"),
    (b"\xff\xfe\x00\x00\x5b\x00\x00\x00\x5d\x00\x00\x00", "OK []"),
    (b"\x5b\x00\x00\x00\x00\x00\x11\x00", "UnicodeDecodeError: 'utf-32-le' codec can't decode bytes in position 4-7: code point not in range(0x110000)"),
    (b"\x00\x5b\x00\x5d", "OK []"),
    (b"\x00\x00\x00\x5b", "JSONDecodeError: Expecting value: line 1 column 2 (char 1)"),
    (b"\x00\x5b", "JSONDecodeError: Expecting value: line 1 column 2 (char 1)"),
    (b"\x5b\x00\x00\xd8\x5d\x00", "JSONDecodeError: Expecting value: line 1 column 2 (char 1)"),
    (b"\xf8\x88\x80\x80\x80", "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xf8 in position 0: invalid start byte"),
    (b"\xf4\x90\x80\x80", "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xf4 in position 0: invalid continuation byte"),
    (b"\x61\x80\x62", "UnicodeDecodeError: 'utf-8' codec can't decode byte 0x80 in position 1: invalid start byte"),
    (b"\xe2\x82\xac\xe2", "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe2 in position 3: unexpected end of data"),
    (b"\x5b\x00\x00\x00\x5d", "UnicodeDecodeError: 'utf-32-le' codec can't decode byte 0x5d in position 4: truncated data"),
    (b"\x5b\x00\x00\x00\x5d\x00", "UnicodeDecodeError: 'utf-32-le' codec can't decode bytes in position 4-5: truncated data"),
    (b"\x5b\x00\x00\x00\x5d\x00\x00", "UnicodeDecodeError: 'utf-32-le' codec can't decode bytes in position 4-6: truncated data"),
    (b"\xff\xfe\x00\x00\x5b\x00\x00\x00\x00\x00\x11\x00", "UnicodeDecodeError: 'utf-32-le' codec can't decode bytes in position 8-11: code point not in range(0x110000)"),
    (b"\x00\x00\xfe\xff\x00\x00\x00\x5b\x00", "UnicodeDecodeError: 'utf-32-be' codec can't decode byte 0x00 in position 8: truncated data"),
    (b"\xfe\xff\x00\x5b\x00", "UnicodeDecodeError: 'utf-16-be' codec can't decode byte 0x00 in position 4: truncated data"),
    (b"\x00\x5b\x00\x5d\xd8\x00", "JSONDecodeError: Extra data: line 1 column 3 (char 2)"),
    (b"\x5b\x00\x00\xdc\x5d\x00", "JSONDecodeError: Expecting value: line 1 column 2 (char 1)"),
    (b"\x7b\x22\x61\x22\x3a\x20\x22\x63\x61\x66\xc3\xa9\x22\x7d", "OK {\"a\": \"caf\u{e9}\"}"),
    (b"\xef\xbb\xbf", "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"),
    (b"", "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"),
    (b"\xff\xfe\x22\x00\x3d\xd8\x00\xde\x22\x00", "OK \"\u{1f600}\""),
    (b"\x00\x00\x00\x22\x00\x01\xf6\x00\x00\x00\x00\x22", "OK \"\u{1f600}\""),
];

#[test]
fn loads_bytes_table_matches_python() {
    for (src, expected) in LOADS_BYTES {
        assert_eq!(
            loads_outcome(loads_bytes(src)),
            *expected,
            "json.loads({src:?})"
        );
    }
}

/// `json.JSONDecoder().raw_decode(s, idx)`: (text, idx, `OK <value> <end>` or the error).
const RAW_DECODE: &[(&str, usize, &str)] = &[
    ("xx [1,2] yy", 3, "OK [1, 2] 8"),
    ("{\"a\": 1} trailing", 0, "OK {\"a\": 1} 8"),
    (
        "caf\u{e9} {\"k\":\"\u{e9}\"}!",
        5,
        "OK {\"k\": \"\u{e9}\"} 14",
    ),
    (
        " [1]",
        0,
        "JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
    ),
    (
        "[1,",
        0,
        "JSONDecodeError: Expecting value: line 1 column 4 (char 3)",
    ),
    (
        "abc",
        3,
        "JSONDecodeError: Expecting value: line 1 column 4 (char 3)",
    ),
    (
        "abc",
        7,
        "JSONDecodeError: Expecting value: line 1 column 8 (char 7)",
    ),
    (
        "\n\nx[{\"a\":}]",
        3,
        "JSONDecodeError: Expecting value: line 3 column 8 (char 9)",
    ),
    ("\u{1f600}[\"\u{1f600}\"]x", 1, "OK [\"\u{1f600}\"] 6"),
    (
        "Here: ```json\n{\"x\": [1, 2.0]}\n``` ok",
        14,
        "OK {\"x\": [1, 2.0]} 29",
    ),
];

#[test]
fn raw_decode_matches_python() {
    for (text, idx, expected) in RAW_DECODE {
        let got = match raw_decode(text, *idx) {
            Ok((v, end)) => format!("OK {} {end}", wire(&v)),
            Err(e) => format!("{}: {e}", e.python_type()),
        };
        assert_eq!(got, *expected, "raw_decode({text:?}, {idx})");
    }
}

#[test]
fn lone_surrogates_inside_strings_are_refused() {
    // CPython accepts these and builds a `str` holding a lone surrogate, which a Rust
    // `String` cannot hold. The parser refuses them with its own message in Python's
    // position format. This pins proposal P-19 of the deviation register, which awaits the
    // owner's decision. Outside a string a lone
    // surrogate fails exactly as in CPython (see the bytes table).
    for (src, pos) in [
        (r#""\ud800""#, 1usize),
        (r#"["ok", "\ud83d\u0041"]"#, 8),
        (r#""\udc00""#, 1),
    ] {
        match loads(src) {
            Err(LoadsError::LoneSurrogate(e)) => assert_eq!(e.pos, pos, "{src}"),
            other => panic!("{src}: expected a lone-surrogate refusal, got {other:?}"),
        }
    }
    match loads_bytes(b"[\"\xed\xa0\x80\"]") {
        Err(LoadsError::LoneSurrogate(e)) => assert_eq!(e.pos, 2),
        other => panic!("expected a lone-surrogate refusal, got {other:?}"),
    }
    // CPython raises its own error first when the rest of the document is wrong.
    assert_eq!(
        loads(r#""\ud800" x"#)
            .err()
            .map(|e| e.to_string())
            .unwrap_or_default(),
        "Extra data: line 1 column 10 (char 9)"
    );
    assert_eq!(
        loads(r#"["\ud800",]"#)
            .err()
            .map(|e| e.to_string())
            .unwrap_or_default(),
        "Illegal trailing comma before end of array: line 1 column 10 (char 9)"
    );
    let text = loads("\"\\ud800\"")
        .err()
        .map(|e| e.to_string())
        .unwrap_or_default();
    assert_eq!(
        text,
        "Unpaired surrogate in string (not representable): line 1 column 2 (char 1)"
    );
}

#[test]
fn indent_variants_follow_python() {
    let v = parse(r#"{"a": [1, {}], "b": "x"}"#);
    let neg = DumpsOptions::python_default().indent(Some(Indent::Spaces(0)));
    assert_eq!(
        dumps(&v, &neg).ok().as_deref(),
        Some("{\n\"a\": [\n1,\n{}\n],\n\"b\": \"x\"\n}")
    );
    let text = DumpsOptions::python_default().indent(Some(Indent::Text("--".into())));
    assert_eq!(
        dumps(&v, &text).ok().as_deref(),
        Some("{\n--\"a\": [\n----1,\n----{}\n--],\n--\"b\": \"x\"\n}")
    );
}
