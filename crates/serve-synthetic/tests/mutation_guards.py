#!/usr/bin/env python3
"""Prove critical tests fail when their guarded behavior is removed."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from q_campaign import configure, executed_cases, python_mutation, rust_mutation

EXPECTED_CASES = {"missing-auth", "declared-length-cap", "frame-accumulation-cap", "unreaped-connections", "silent-stream-failure", "missing-release", "false-terminal", "no-shutdown-grace", "first-host-wins", "flat-error-type", "early-permit-release", "skipped-provider-cancellation", "invalid-terminal-accepted", "consumer-authored-usage", "eof-as-provider-return", "omitted-eof-cancellation", "forgotten-future-at-cleanup-bound", "saturating-usage-total", "cloud-destination", "redirect-follow"}



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--campaign-seconds", type=int, default=2700)
    args = parser.parse_args()
    pristine = Path(__file__).resolve().parents[1]
    configure(pristine, args.root, args.evidence, args.matrix, args.campaign_seconds)
    if args.scratch.exists():
        raise RuntimeError("scratch path must not exist")
    args.scratch.mkdir(parents=True, mode=0o700)
    args.target.mkdir(parents=True, exist_ok=True)

    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "missing-auth",
        "if !valid_auth(request.headers().get(AUTHORIZATION), &state.token) {",
        "if false {",
        "health_and_models_enforce_the_boundary",
    )
    # F3: the declared-length cap and the accumulated-frame cap are separate
    # defences and are mutated separately. Mutating both at once (as the former
    # "excess-body" mutant did) let a single test conceal a missing check: a
    # request that declares an oversized length *and* sends one is still caught
    # by frame accumulation alone.
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "declared-length-cap",
        "if length > MAX_BODY_BYTES {",
        "if length > usize::MAX {",
        "invalid_declared_length_is_rejected_by_the_parser",
    )
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "frame-accumulation-cap",
        "if bytes.len().saturating_add(data.len()) > MAX_BODY_BYTES {",
        "if bytes.len().saturating_add(data.len()) > usize::MAX {",
        "chunked_body_exceeding_accumulated_limit_is_rejected",
    )
    # F1: removing in-loop reaping must break the reaping test specifically.
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "unreaped-connections",
        "            _ = tokio::time::sleep(SHUTDOWN_POLL) => state.reap_cleanup(),\n",
        "",
        "repeated_connections_are_reaped_during_normal_operation",
    )
    # F2: suppressing the streaming error terminal must break the timeout test.
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "silent-stream-failure",
        '                        let _ = send_backend_error_code(&sender, "generation_timeout", message).await;\n',
        "",
        "stream_generation_timeout_emits_bounded_error_event",
    )
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "missing-release",
        "if released && joined {\n"
        "                self.metrics.backend_active.fetch_sub(1, Ordering::SeqCst);",
        "if released && joined {\n"
        "                self.metrics.backend_active.fetch_add(1, Ordering::SeqCst);",
        "disconnect_releases_stream_ownership",
        1,
        "src/cleanup_owner.rs",
    )
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "false-terminal",
        "BackendEvent::Failed(BackendFailure::Generation),",
        "BackendEvent::Finished { reason: BackendFinishReason::Stop, usage: ActualUsage { prompt_tokens: 1, completion_tokens: 1 } },",
        "stream_failure_has_no_success_terminal",
        1,
        "src/backend.rs",
    )
    # Shutdown must not cut an active stream off before its terminal reaches
    # the wire; removing the grace window must not survive.
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "no-shutdown-grace",
        "    let deadline = tokio::time::Instant::now() + SHUTDOWN_GRACE;\n"
        "    while state.metrics.backend_active.load(Ordering::SeqCst) > 0\n"
        "        && tokio::time::Instant::now() < deadline\n"
        "    {\n"
        "        state.reap_cleanup();\n"
        "        tokio::time::sleep(SHUTDOWN_POLL).await;\n"
        "    }\n",
        "",
        "shutdown_delivers_a_server_shutdown_event_to_an_active_stream",
    )
    # F8: first-Host-wins must not survive.
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "first-host-wins",
        "    let mut values = headers.get_all(HOST).iter();\n"
        "    let (Some(host), None) = (values.next(), values.next()) else {\n"
        "        return false;\n"
        "    };\n",
        "    let Some(host) = headers.get(HOST) else {\n        return false;\n    };\n",
        "duplicate_host_headers_are_rejected",
    )
    # F5: collapsing every error type back to invalid_request_error must not
    # survive.
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "flat-error-type",
        'StatusCode::UNAUTHORIZED => "authentication_error",',
        'StatusCode::UNAUTHORIZED => "invalid_request_error",',
        "error_types_are_classified_by_status",
    )
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "early-permit-release",
        "        let mut guard = Some(guard);",
        "        drop(guard);\n        let mut guard = None;",
        "uncooperative_valid_eof_drops_future_before_release_and_preserves_wire_precedence",
        1,
        "src/lib.rs",
        "backend_semantics",
    )
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "skipped-provider-cancellation",
        "    cancel.send_replace(true);",
        "    cancel.send_replace(false);",
        "timeout_cancels_owned_provider_before_releasing_permit",
        1,
        "src/lib.rs",
        "backend_semantics",
    )
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "invalid-terminal-accepted",
        "        if self.event_count > MAX_BACKEND_EVENTS || self.terminal.is_some() {",
        "        if self.event_count > MAX_BACKEND_EVENTS {",
        "malformed_provider_terminals_never_become_nonstream_success",
        1,
        "src/lib.rs",
        "backend_semantics",
    )
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "consumer-authored-usage",
        '"usage":{"prompt_tokens":usage.prompt_tokens,"completion_tokens":usage.completion_tokens,"total_tokens":total_tokens}',
        '"usage":{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}',
        "admission_projection_model_and_provider_usage_are_authoritative",
        1,
        "src/lib.rs",
        "backend_semantics",
    )
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "eof-as-provider-return",
        "                        cancel_owned_backend(&state, &cancel, &mut future, &mut future_state, CleanupTrigger::Eof).await;",
        "                        future_state = BackendFutureState::Returned;",
        "eof_before_return_observes_true_cancellation_and_cooperative_completion",
        1,
        "src/lib.rs",
        "backend_semantics",
    )
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "omitted-eof-cancellation",
        "    cancel.send_replace(true);",
        "    if _trigger != CleanupTrigger::Eof {\n        cancel.send_replace(true);\n    }",
        "eof_before_return_observes_true_cancellation_and_cooperative_completion",
        1,
        "src/lib.rs",
        "backend_semantics",
    )
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "forgotten-future-at-cleanup-bound",
        "        let owned_future = future.take().expect(\"polling backend future\");\n        drop(owned_future);",
        "        let owned_future = future.take().expect(\"polling backend future\");\n        std::mem::forget(owned_future);",
        "uncooperative_valid_eof_drops_future_before_release_and_preserves_wire_precedence",
        1,
        "src/lib.rs",
        "backend_semantics",
    )
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "saturating-usage-total",
        "        self.prompt_tokens.checked_add(self.completion_tokens)",
        "        Some(self.prompt_tokens.saturating_add(self.completion_tokens))",
        "usage_overflow_is_safe_protocol_failure_in_both_response_modes",
        1,
        "src/backend.rs",
        "backend_semantics",
    )
    python_mutation(
        pristine,
        args.scratch,
        args.python,
        "cloud-destination",
        "        self.require_loopback(request)\n",
        "        pass\n",
    )
    python_mutation(
        pristine,
        args.scratch,
        args.python,
        "redirect-follow",
        "        transport=LoopbackGuardTransport(redirect_inner),\n        follow_redirects=False,\n",
        "        transport=LoopbackGuardTransport(redirect_inner),\n        follow_redirects=True,\n",
    )
    if executed_cases != EXPECTED_CASES:
        raise RuntimeError(f"mutation campaign census mismatch missing={sorted(EXPECTED_CASES - executed_cases)}")
    print(f"MUTATION_GUARDS_OK count={len(executed_cases)}")


if __name__ == "__main__":
    main()
