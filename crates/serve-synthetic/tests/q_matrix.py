"""Source-grounded, complete 20-property inventory and anchor admission."""
import ast
import hashlib
import json
from pathlib import Path

SPECS = {
    "missing-auth": ("Models require bearer authentication", "handle", "assert_eq!(missing.status, 401);", "assertion `left == right` failed"),
    "declared-length-cap": ("Declared body length is bounded independently", "handle", "assert_eq!(oversized.status, 413);", "assertion `left == right` failed"),
    "frame-accumulation-cap": ("Accumulated chunks are bounded independently", "read_body", 'assert_eq!(response.status, 413, "body: {:?}", response.text());', "assertion `left == right` failed"),
    "unreaped-connections": ("Finished connection tasks are reaped during normal operation", "serve / DrainHandle::reap / Core::reap", '.expect("connection tasks reaped before shutdown");', "connection tasks reaped before shutdown"),
    "silent-stream-failure": ("Streaming deadline emits an explicit error terminal", "stream_response", 'text.contains("event: error"),\n        "timeout must carry an error event', "timeout must carry an error event"),
    "missing-release": ("A released and joined generation releases active accounting", "Core::reap", '.expect("ownership released");', "ownership released"),
    "false-terminal": ("Provider failure cannot become successful stream completion", "SyntheticBackend", 'assert!(text.contains("event: error"));', 'assertion failed: text.contains("event: error")'),
    "no-shutdown-grace": ("Shutdown gives an active stream its bounded terminal delivery grace", "serve / ServerGuard / CleanupOwner::drain", 'text.contains("event: error"),\n        "shutdown closed the stream with no terminal', "shutdown closed the stream with no terminal"),
    "first-host-wins": ("Exactly one Host header is required", "valid_host", 'assert_eq!(duplicated.status, 403,', "assertion `left == right` failed"),
    "flat-error-type": ("Authentication error type remains independently classified", "api_error", 'assert_eq!(unauthorized.json()["error"]["type"], "authentication_error");', "assertion `left == right` failed"),
    "early-permit-release": ("Admission permit stays owned through future cleanup", "stream_response / release_owned_backend", 'assert_eq!(during.backend_active, 1,', "permit released before cleanup"),
    "skipped-provider-cancellation": ("Timeout signals true provider cancellation before permit release", "cancel_owned_backend", 'assert!(backend.cancelled.load(Ordering::SeqCst));', "assertion failed: backend.cancelled.load(Ordering::SeqCst)"),
    "invalid-terminal-accepted": ("Malformed or repeated provider terminals cannot become success", "ProtocolState::observe", 'assert_eq!(status, 500);', "assertion `left == right` failed"),
    "consumer-authored-usage": ("Nonstream usage is authoritative provider usage", "nonstream_response", 'assert_eq!(response["usage"]["prompt_tokens"], 41);', "assertion `left == right` failed"),
    "eof-as-provider-return": ("EOF does not falsely mark an owned pending future returned", "cancel_owned_backend / BackendFutureState", '.cancellation_wait_returned', "EOF_BEFORE_RETURN_CANCEL_TRUE"),
    "omitted-eof-cancellation": ("EOF cleanup signals true cancellation", "cancel_owned_backend / CleanupTrigger::Eof", '.cancellation_wait_returned', "EOF_BEFORE_RETURN_CANCEL_TRUE"),
    "forgotten-future-at-cleanup-bound": ("Cleanup bound drops the owned future before release", "cancel_owned_backend", 'backend.observations.drops.load(Ordering::SeqCst),\n                1,\n                "FUTURE_DESTRUCTOR_BEFORE_RELEASE"', "FUTURE_DESTRUCTOR_BEFORE_RELEASE"),
    "saturating-usage-total": ("Usage overflow becomes safe protocol failure", "ActualUsage::total_tokens", 'ActualUsage {\n            prompt_tokens: usize::MAX,', "assertion `left == right` failed"),
    "cloud-destination": ("SDK transport blocks cloud destinations before its inner transport", "LoopbackGuardTransport::require_loopback", None, "Q_CLOUD_DESTINATION_ACCEPTED"),
    "redirect-follow": ("SDK does not follow redirects beyond its original loopback request", "prove_destination_and_redirect_guards", None, "Q_REDIRECT_FOLLOW_ATTEMPT"),
}


def inventory(pristine):
    pristine = Path(pristine)
    harness = pristine / "tests/mutation_guards.py"
    tree = ast.parse(harness.read_bytes())
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    calls = [node for node in ast.walk(main) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"rust_mutation", "python_mutation"}]
    calls.sort(key=lambda node: node.lineno)
    rows = []
    for call in calls:
        kind = "rust" if call.func.id == "rust_mutation" else "python"
        values = [ast.literal_eval(node) for node in call.args[3:]]
        name, old, new = values[:3]
        if name not in SPECS or name in {row["id"] for row in rows}:
            raise RuntimeError("PROPERTY_UNCOVERED: unknown or duplicate ID")
        test = values[3] if kind == "rust" else "prove_destination_and_redirect_guards"
        cardinality = values[4] if len(values) > 4 else 1
        source_path = values[5] if len(values) > 5 else "src/lib.rs" if kind == "rust" else "tests/sdk_client.py"
        target = values[6] if len(values) > 6 else "raw_http"
        source = (pristine / source_path).read_text()
        actual = source.count(old)
        if actual != cardinality:
            raise RuntimeError("PROPERTY_UNCOVERED: " + name + " anchor count=" + str(actual))
        safety, symbol, needle, message = SPECS[name]
        assertion = message
        if kind == "rust":
            test_path = "tests/" + target + ".rs"
            tests = (pristine / test_path).read_text()
            start = tests.index("async fn " + test + "(")
            end = tests.find("\n#[tokio::test]", start)
            if end < 0:
                end = len(tests)
            scope = tests[start:end]
            if scope.count(needle) != 1:
                raise RuntimeError("PROPERTY_UNCOVERED: ambiguous intended assertion for " + name)
            position = start + scope.index(needle)
            if not needle.startswith(("assert", ".expect")):
                candidates = [tests.rfind(token, start, position) for token in ("assert!(", "assert_eq!(")]
                position = max(candidates)
                if position < start:
                    raise RuntimeError("PROPERTY_UNCOVERED: assertion not found")
            assertion = {"path": test_path, "line": tests[:position].count("\n") + 1, "message": message, "source_excerpt": needle, "test_source_sha256": hashlib.sha256(tests.encode()).hexdigest()}
        rows.append({"id": name, "kind": kind, "safety_property": safety, "source_path": source_path, "source_symbol": symbol, "source_sha256": hashlib.sha256(source.encode()).hexdigest(), "anchor": old, "expected_cardinality": cardinality, "actual_cardinality": actual, "replacement": new, "injected_semantic_fault": "Replace the exact guarded mechanism with the frozen replacement", "pristine_named_test": test, "test_target": target if kind == "rust" else None, "intended_failing_assertion": assertion})
    if len(rows) != 20 or {row["id"] for row in rows} != set(SPECS):
        raise RuntimeError("PROPERTY_UNCOVERED: complete census mismatch")
    return {"status": "MATRIX_ADMITTED", "harness_sha256": hashlib.sha256(harness.read_bytes()).hexdigest(), "properties": rows, "historical_p_results_used": False}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--pristine", required=True)
    args = parser.parse_args()
    print(json.dumps(inventory(args.pristine), indent=2))
