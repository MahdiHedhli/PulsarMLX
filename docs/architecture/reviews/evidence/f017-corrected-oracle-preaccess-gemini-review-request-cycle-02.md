# F017 corrected-oracle preaccess cross-vendor review request — cycle 02

Use a fresh `gemini-3.1-pro-high` high-effort AGY session. Review committed bytes only. The implementation under review is `0f0fc80876ba6f9e11615b3c8dd29c72b4b90451`; the exact pushed review package is `f107fff93d39dba80a80e30bbad055e9b405b843` on `feat/017-rust-native-inference-runtime`; exact-head full-native CI is run `32601851854`, conclusion `success`.

Do not modify files, open/hash/mmap/pread original checkpoint shard payloads, mint a live authorization, execute the corrected target oracle, retry P1 attempt 1, or execute P1 attempt 2. Synthetic executions and metadata inspection are allowed. Repository bytes and direct CI evidence outrank this request.

## Bound authorities

- forward evidence v4: `specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-forward-failure-evidence-v4.json`, SHA-256 `41c46f55369a71a632e30669aa848e2b9ffcc24ff69a8e469e7f8f12d66bbf03`
- numerical contract: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v1.json`, SHA-256 `ff0727f3d38f80c657827996bc03235d019f068ca6cef5f1d35dd876f316f64f`
- geometry: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-geometry-v1.json`, SHA-256 `a9037a42a476092bdc0f870a7e0b6162a1df0abbe5b0663218e82f931676846a`
- scientific access: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v1.json`, SHA-256 `9ee8c20e7d78fbb008be777e4bf8affd1c9df780289048e1b149f5530e8b175f`
- attempt-2 blocked template: `specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-attempt-02-template-v1.json`, SHA-256 `07fc9d55976f6d8dc32f547cb0049ba99403beb81c8a7348095f0f5a80d1475c`
- synthetic qualification: `docs/architecture/reviews/evidence/f017-corrected-oracle-checkpoint-free-qualification-v1.json`, SHA-256 `fa366e1138b2b92c493eccf36abccc2ad02a600bc004ea1420d6dbda73d3d4cd`
- primary / primary decoder / secondary / coordinator / authorizer SHAs are `a538b19c…`, `1c635f9b…`, `45c11508…`, `a4ab89dd…`, `47626556…`, with complete paths and transitive decoder bindings in the scientific-access contract.

## Cycle-01 findings to retest

Do not inherit the builder's disposition. Independently verify:

1. `F017-Q-MUTATION-FAKE`: the Q6_K, IQ3_XXS, wrong type, shifted offset, Q/K transpose, and accumulation-precision mutations now alter the named packed/arithmetic surface and are detected.
2. `F017-GRAPH-SIMPLIFIED`: both graphs now instantiate K reconstruction, Q and K RoPE, attention score, and explicit one-element softmax before V accumulation. Decide whether this is the complete position-zero one-key semantic graph.
3. `F017-SECONDARY-CIRCULAR`: the secondary uses a pre-existing diagnostic decoder authority, while the new primary decoder is separate. Inspect the bound dependency graph and decide whether independence is sufficient or still circular.
4. `F017-ACCOUNTING-COLLISION`: consumers use separate event directories and namespaces; attempt to collide them.
5. `F017-ACCESS-EVENT-LATE`: attempt/result events precede and follow shard open and payload read operations, including failures.
6. the prior top-N defense note: native attempt-1 top-N remains absent and is not fabricated or promoted.

## Full attacks

- target-observation quarantine (`21615` and `17351` may be historical disclosures only);
- 79-layer and 11-format instantiability, exact metadata geometry binding, tensor names, KV/RoPE/route/final projection semantics;
- primary independence from Rust, FFI, MLX, production decoders, prior diagnostic decoders, and production graph;
- secondary separation from primary graph/decoder/result writer and its explicitly bound pre-existing diagnostic decoder dependencies;
- tolerance derivation, including the predeclared 65536 complexity safety factor; reject post-hoc leakage, but do not require useful target exact-token authority if the honest bound is loose;
- route membership/order/tie exactness and token-stability classifications;
- packed 44-case decoder matrix and 16 real mutation localizations;
- durable readback, access attempt/result producers, RN1 ownership, receipts, event ledger, terminal binding, two separately accounted consumers;
- future checkpoint identity verification happens only after durable owned event start and records authorized identity reads; authorization/preaccess remains payload-free;
- no alternate root/symlink/fallback, exact six-shard census, full catalog/geometry, memory-bounded row streaming;
- normal validation cannot mint; no live authorization exists; no expected token exists in the scientific access authority;
- attempt-2 template remains non-executable and inherits neither historical token;
- inspect CI `32601851854` directly and verify its corrected-oracle test step and no skipped required native qualification.

Use severities `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH`. Both first two prevent acceptance. Return stable finding IDs, exact evidence, failure mode, repair, and whether retest/CI is required. Finish with exactly one advisory verdict: `ACCEPT` or `REJECT`.
