# Independent bounded-wait static review and disposition

Base: `ebe7ddfe47bbb85ff85074981cad2363a382bf2a`. The [scanned, frozen packet](bounded-wait-review-packet-2026-10-08.json) and [manifest](bounded-wait-review-manifest-2026-10-08.json) cover only the bounded-wait objective, scheduler, acceptance/legacy scheduler tests, fixture-store source and page catalog. No weights, checkpoint Python, credentials or unrelated data were submitted. The packet is 82,068 UTF-8 bytes; its SHA-256 and exact per-file hashes are in the manifest. The final source still matches the reviewed code packet.

Reviewer: explicitly selected permitted `gemini-3.8-flash-high` via the existing `agy` route, conversation `130bebf3-a1d8-4e0e-bc77-7611b1e0fc38`. No Claude/Anthropic identity or alternate account was used, no credentials or permission-rule configuration were changed, and no purchase was made. The request prohibited tools, execution, browsing, modification and unrelated file access.

## Review observation and recovery

The first CLI invocation rejected an incorrectly formatted timeout before submitting a request; [setup diagnostic](bounded-wait-gemini-cli-setup-stderr-2026-10-08.txt). The corrected 180-second observation returned [empty partial metadata](bounded-wait-gemini-review-2026-10-08.json) while its [diagnostic](bounded-wait-gemini-review-stderr-2026-10-08.txt) reported the turn still in progress. This was not counted as a verdict or reason to restart. Attaching an observer to the same conversation subsequently showed it was interrupted, with thought output but no final report. Broad `/private/tmp` trust was declined; the observer used an isolated directory with only the scanned packet. Unrelated CLI permission-rule warnings were left unchanged and no invalid rule was used to grant access.

The same conversation was continued after that authoritative terminal observation, using its existing exact packet and the same Gemini identity. The [final raw report](bounded-wait-gemini-resumed-review-2026-10-08.json) has status `SUCCESS`, two turns, a nonempty final response and verdict **ACCEPT**. Its [diagnostic](bounded-wait-gemini-resumed-review-stderr-2026-10-08.txt) contains only the CLI mode warning. No additional source or data was supplied in the continuation. There is no independent verdict in the empty partial result; the nonempty final report is the evidence.

## Local triage

The reviewer found no concrete correctness, lifetime, contention, deadline, identity, cancellation or accounting defect. Its observations were checked against the exact source and generated-fixture tests:

- Fit-capable demands defer without dropping reservations; completion/release/finish makes old pages evictable and admits the waiting page. Deadline expiry or explicit cancellation keeps original pending IO/GPU ownership until drainage.
- Impossible page size is checked before IO-slot exhaustion. Actual demands retain priority over speculative hints, whose invalidated reservations remain until original IO completes.
- Fixed monotonic deadlines do not renew on duplicate demand or unrelated progress. IO admission is defined progress; promoted-hint completion clears its wait. Callers must poll the cooperative watchdog. This does not implement an autonomous backend deadline or qualify production latency.
- Exact ticket objects and original integer-compatible in-process lease handles are required. Copying/reconstructing values cannot acknowledge IO/GPU completion. These are honest-caller guards, not a Python in-process sandbox.
- The two nonblocking suggestions were removing redundant capacity guards and adding an expired page key to diagnostics. Neither changes required behavior; both are deferred to preserve the exact accepted code.

The report's `file:///scripts/...` links are not real workspace links and some language overstates “true” completion: the GPU acknowledgement is still a synthetic protocol claim, not an actual fence. `Limits` models byte/count caps; the real 48/40/16 GiB planning defaults are preserved separately and tested. Passing these fixtures is not a process-footprint bound or numerical/model qualification. The existing fixture store's derived-view and independent physical-observation limitations remain unchanged; the additive owning adapter and prior review evidence remain intact.

## Acceptance and remaining gates

[Validation](bounded-wait-validation-2026-10-08.json) records **13 focused tests** and **124 applicable Qwen tests**, exact commands, source hashes and raw outputs. Tests use fake clocks and tiny generated verified files; no real checkpoint, package install, local MLX/model loading, inference, benchmark, weights download or GLM Studio access occurred. No numerical operation or reference tolerance changed. Diff/secret/large-file review and a local checkpoint precede separately recognized normal-push authority and exact-commit CI. The goal remains incomplete until remote head and terminal CI conclusions are verified.

The frozen packet is stored as a JSON wrapper to preserve every submitted byte, including numbered blank-line separators, while passing repository whitespace checks. Reconstruct UTF-8 `exact_submitted_text` and verify the original packet hash; this encoding change does not change reviewer input or source.
