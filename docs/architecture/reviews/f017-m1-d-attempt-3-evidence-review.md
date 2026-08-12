# F017 M1-D Attempt 3 Evidence Review

**Verdict: M1-D ATTEMPT 3 ACCEPTED**

Date: 2026-08-12

## Source, authorization, and admission

The only attempt-3 production invocation used runtime
1c7705c130d5909bb4523d70bc7ec45e974e1b24, reviewed tooling
2e84a4e0899cea333deadb2c7f4a5022766e0784, and immutable execution config
42fb54d08c2c8ee8c7b06360e04743e8c8a976df649e1a0b8ef505c94c01a9fa.
The non-consuming preflight returned READY_TO_EXECUTE_ATTEMPT_3; the config
bound the exact repository-relative activation fixture
specs/017-rust-native-inference-runtime/fixtures/f017-m1d-projection-oracle-v1.json.
Attempts 1 and 2 remain immutable rejections at evidence hashes
a5aefaaf59583dad87765303e159986c895017c20ea80eb874cd447ad80f9a62 and
6a87c36c380fb43393bc79cdc4e22e59bb81c0425ad0285017d6a1bc00dd79f6.

Production admission used production_reviewed, measured-host telemetry, and
the exact arm64 MLX 0.31.2 / MLX-C 0.6.0 libraries. Available memory was
86,504,816,640 bytes against a 17,179,869,184-byte floor; pressure and thermal
state were normal, swap use was 125,829 bytes, both relevant volumes had
352,055,169,024 free bytes, competing inference was clear, and port 1234 had
no listener.

## Boundary and independent oracle

The candidate read exactly one 3,760,128-byte range for
blk.0.attn_kv_a_mqa.weight and verified packed payload SHA-256
ff2b6a0e14f3e180ba6a8a8522ef4569c9cb82a0f10708f66da794305e3ee4cc.
The independently decoded f32 matrix hash was
2652de151b122aee24cdeb7e80b303831b6b7f42a82daaf0d9ca51f21c6afe75.
The frozen activation remained
dfc1df6cc6efa38c5c0f5bf086757ed78baf4cfc6f721da1e0ae7f73560193c2.

The read-only oracle file hash is
330522cecbf088a32ce2f54ed932dd34a5db14daa6c880272c61b2eaec3d4fe4;
the enclosing package hash is
98e579572e2a61071311f9bdeee169c63b8bb8206f0d105b22a052652548c7ba.
Reference output SHA-256 is
2e0add595e590ec1befec21402d059cb73ebcc6f0c63029e36901b4b6db8d96b,
and the Tier-B row-bound-vector SHA-256 is
c1efe56ffabf38d0a413f9e901a886b59730111c43a7644e560ec451b9c6b2a7.
The derived global limits were maximum absolute error 0.5095961046235974,
RMSE 0.1495906979161905, and cosine minimum 0.867507213998622.

Oracle completion marker oracle_finalized_sequence_0 at 1786572710986781000
strictly preceded candidate marker candidate_started_sequence_1 at
1786572760500622000. The runner validated and rehashed the same oracle before
candidate start and after teardown; oracle_validated_before_candidate and
structural_order_valid are true.

## Production numerical result

All ten ordinals 0 through 9 produced the identical canonical f32 output hash
709789007d3dfca01a9265220fc68cbf79f3583614ce595262f082e2adaee8eb.
The selected output is the recorded ordinal-9 result. Qualification recorded
566 bit mismatches, maximum absolute error 0.00002574920654296875, RMSE
0.000003380988257581472, and cosine similarity 0.9999999999987387. Every
per-row and global Tier-B check passed; signed-zero and non-finite policies
are part of the fail-closed PASS result. Classification is
numerically_qualified_greedy_not_applicable with greedy applicability
not_applicable.

Recorded stage timings were 0.000764083 s storage, 0.031327458 s decode,
0.361281042 s qualification scaffold, 0.00022375 s backend import, and
0.018405625 s production compute/sync/readback. These buckets sum to
0.412001958 s; independent-preparer and runner orchestration wall are not
represented as a canonical evidence timing bucket.

## Dispatch, isolation, and lifecycle

Evidence records one conceptual projection, ten native dispatches, one
candidate Q8_0 decode, and zero direct, production-scaffold, explicit-reference,
fallback, backend-error, expert, layer, or logits dispatches. P1 is false; P2,
golden-eight, and Feature 018 are outside and were not invoked by this
single-boundary binary path.

Lifecycle reconciled after teardown: managed 2/2, derived 10/10, callbacks 2,
default CPU streams 1/1, owned streams 1/1, active contexts 0, and singleton
inactive. Registration/generation/owner-token domains are explicitly
not_applicable, not measured zeros.

## Review answers

1. One reviewed real matrix boundary only? **Yes.**
2. Immutable config and exact activation path used? **Yes.**
3. Oracle independent and finalized before candidate? **Yes.**
4. Canonical production MLX path genuine? **Yes.**
5. Exactly ten repeat hashes and all equal? **Yes.**
6. Frozen Tier-B contract passed without retuning? **Yes.**
7. Fallback/errors zero? **Yes.**
8. Lifecycle fully reconciled? **Yes.**
9. Public evidence free of private absolute paths? **Yes.**
10. Is a separately reviewed one-expert M1-E boundary now meaningful? **Yes,
    but it is not authorized by this review.**

The banked public evidence SHA-256 is
dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c.
Attempt 3 is consumed. No retry or M1-E execution occurred.
