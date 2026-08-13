# F017 M1-E Independent Adversarial Review

**Reviewer role:** INDEPENDENT ADVERSARIAL

**Verdict: GO FOR ONE M1-E REAL EXPERT**

## Reviewed binding

- runtime implementation: `466770362e3066fa5fd9827ec1f454e03afe3006`
- tooling/test qualification: `3387bb6d4508eb04e672dc6194da2855ba72f072`
- reviewed package head: `f3a7ba8f3a7eb52dbf48c6929e23835e5c18eeea`
- handoff SHA-256: `2325f9b2964b5c1120864fbaa4d3fda875f8d263154d783bf02b6ad47e78e531`
- immutable execution-config SHA-256: `7f69550bfd7ccd5e820f23d2bcce7f0e287d2c2bfc5f1ae2adb59ec5467b0a1b`
- package-head CI: `31656082515`, both Apple jobs green

## Adversarial conclusions

1. The selected boundary is unambiguous: layer 3/expert 15, with the exact
   gate/up/down catalog identities and ranges. Selection preceded M1-E payload
   or candidate observation.
2. The 6,144-element input is independently generated and content-bound. The
   independent oracle cannot import candidate, Rust reference, MLX, FFI, or
   candidate-produced output.
3. Exact arithmetic and the composed Tier-B contract were frozen first. The
   contract is immutable, candidate-independent, finite-only, signed-zero
   exact, and uses the only valid success class
   `numerically_qualified_greedy_not_applicable`.
4. Checkpoint access is capped at three named payloads, one shard open, three
   positional reads, and 11,304,960 compressed bytes. A second expert, router,
   shared expert, layer, output head, logits, wildcard, or neighboring tensor
   is not representable by the validated config.
5. Human-assembled execution inputs cannot override the package: the future
   launcher accepts only the immutable config path and its SHA-256. Repository
   and private-package namespaces remain typed, content-hashed, relocation
   safe, and cwd independent.
6. Ten complete expert repeats require four hashes per ordinal and independent
   re-derivation of equality. Thirty native matvec dispatches must reconcile to
   one expert; scaffold, reference, fallback, and backend-error dispatches must
   be zero.
7. PASS follows oracle ordering, execution, teardown, lifecycle, dispatch,
   repeat, path/config, numerical, and final evidence reconciliation. Injected
   stale oracle, order inversion, intermediate divergence, wrong expert/tensor,
   truncation, fallback, lifecycle, consumed-attempt, and config-mutation cases
   all fail closed.
8. Accepted M1-A through M1-D evidence is directly bound. M1-F and P1 remain
   blocked regardless of the future M1-E result.

CI `31656082515` exercised the canonical native real-shaped path and all
load-bearing negative gates at the exact reviewed package head. No relevant
test was ignored. No real M1-E payload was accessed and M1-E was not executed.
