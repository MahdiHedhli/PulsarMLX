# F017 Canonical Runner Adversarial Review Packet

## Review request

Please answer:

> Is the canonical runner now real enough to begin staged M1 checkpoint
> integration at M1-A/B/C without hiding behind synthetic/reference paths?

The requested disposition is GO, GO WITH REQUIRED FIXES, or NO-GO. This packet
does not request real-checkpoint execution or P1 authorization.

## Accepted numerical foundation

- R7 exact expert scaffold: golden-identical.
- R7 production expert: frozen Tier-B qualified, greedy not applicable.
- R8 top-8 plus shared: frozen Tier-B qualified with exact selected expert IDs,
  greedy not applicable.
- R9 MLA/DSA: exact scaffold plus production R9 v2 qualification.
- R10 complete layer: exact scaffold plus production R10 v2 qualification.
- R7 vocabulary amendment is explicit; R9/R10 v1 remain historical and v2 are
  the active immutable contracts.

The accepted numerical basis and audit trail are documented in:

- [`f017-r7-numerical-review-packet.md`](f017-r7-numerical-review-packet.md)
- [`f017-contract-versioning-cleanup.md`](f017-contract-versioning-cleanup.md)
- [`f017-r9-r10-numerical-boundary-report.md`](f017-r9-r10-numerical-boundary-report.md)

## R11 final-output boundary

- Independent Python/NumPy generator; no Rust candidate, MLX, or checkpoint.
- Canonical IEEE-754 fixture for final hidden, RMSNorm, Q4_K output head,
  logits, top-k scores, and argmax.
- Exact scaffold is golden-identical.
- Ten production repeats satisfy frozen Tier B.
- Top-k IDs and argmax are exact.
- Classification is `numerically_qualified_greedy_identical`; greedy
  applicability is `applicable`.
- Ten native dispatches, zero fallback/errors, lifecycle reconciled.

Evidence:

- [`f017-r11-final-output-oracle-v1.json`](../../../specs/017-rust-native-inference-runtime/fixtures/f017-r11-final-output-oracle-v1.json)
- [`production-r11-tier-b-v1.json`](../../../specs/017-rust-native-inference-runtime/contracts/production-r11-tier-b-v1.json)
- [`f017-r11-final-output-production-v1.json`](evidence/f017-r11-final-output-production-v1.json)

## R12 actual-binary end-to-end boundary

The checked-in fixture is a two-layer synthetic GLM-DSA model split across two
GGUF-v3 files. It has 105 validated tensor contracts and exercises embedding,
MLA/DSA, routing, eight routed experts, one shared expert, residuals, final
RMSNorm, Q4_K output head, logits, and selection.

Both exact and production runs execute through `f017-glm52-runner` with the
same CLI, evidence writer, `RunnerTensorStore`, fixture tensor map, layer loop,
and fail-closed dispatch. Fixture mode changes model identity only; it does not
select a second engine. Production uses `MlxContext` for 69 large matvecs per
repeat and explicit Rust CPU semantics for small deterministic operations.

- Exact: ten repeats, token 10, 690 scaffold dispatches, golden-identical.
- Production: ten repeats, token 10, 690 native dispatches.
- Routes, top-k, and argmax are exact.
- Production final logits satisfy frozen Tier B.
- Fallback/backend errors are zero.
- 1,380 managed events, 690 derived events, 1,380 callbacks, and one owned
  stream reconcile after production teardown.

Evidence:

- [`f017-r12-tiny-model`](../../../specs/017-rust-native-inference-runtime/fixtures/f017-r12-tiny-model/)
- [`f017-r12-tiny-model-exact-v1.json`](evidence/f017-r12-tiny-model-exact-v1.json)
- [`f017-r12-tiny-model-production-v1.json`](evidence/f017-r12-tiny-model-production-v1.json)

## Failure behavior

Actual-binary tests reject duplicate JSON keys, missing contracts, wrong
shapes, unsupported quantization, and truncated shards. Exact fixture execution
supports deterministic pre-layer and between-layer cancellation injection and
banks `CANCELLED`, never PASS. An injected production-adapter failure
synchronizes and releases the context and owned stream before banking a failure.
Fresh-output and atomic-writer failure behavior are covered by evidence tests.

## CLI and evidence

The same binary retains:

- `--dry-run`
- `--adapter-preflight-only`
- `--checkpoint-identity-only`
- `--fixture-mode`

The evidence schema binds source/environment/model identities, admission,
input, layer timing, storage, numerical classification, greedy applicability,
top-k/argmax identity, dispatch, residency, lifecycle, result, and first
failure. Duplicate keys fail closed and public paths are repository-relative.

## Quantization and operation coverage

Checkpoint-free runner coverage includes F32, Q8_0, and Q4_K at the composed
R12 boundary plus previously qualified Feature 017 decoder fixtures. This does
not prove that every format in the real GLM catalog is executable. The real
format inventory and tensor ranges remain staged R13/M1 work.

## Explicit omissions

- No real checkpoint was opened or hashed.
- No canonical P1 command is published.
- Feature 018 IQ2/IQ3 direct Metal kernels are absent.
- Output-head native-ready residency is absent.
- Full real output-head memory and timing are untested.
- Real-shape MLA/DSA, expert, and logits boundaries remain untested.
- This is not a product-readiness or performance claim.

## Review focus

1. Does R12 genuinely use the production adapter and canonical runner path?
2. Are the explicit Rust CPU boundaries acceptable for staged M1 integration?
3. Can any fallback or fixture shortcut hide a missing runtime operation?
4. Are lifecycle and cancellation failures complete enough for M1-A/B/C?
5. Are independent oracle provenance and contract inheritance sufficiently
   separated from the candidate implementation?
6. Does any gap require another checkpoint-free gate before M1-A/B/C?

## Admission state

- R11: passed, adversarial review pending.
- R12: passed, adversarial review pending.
- Internal implementation review: pending.
- M1-A/B/C: blocked pending reviews.
- Real checkpoint: blocked.
- P1: blocked.
