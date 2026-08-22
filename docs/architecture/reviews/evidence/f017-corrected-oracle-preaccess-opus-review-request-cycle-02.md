# F017 corrected full-checkpoint oracle preaccess final review — cycle 02

You are the final independent adversarial reviewer. Use a fresh `claude-opus-5` high-effort session. Review committed bytes from a clean detached checkout. The bound implementation is `0f0fc80876ba6f9e11615b3c8dd29c72b4b90451`; the exact pushed review package is `f107fff93d39dba80a80e30bbad055e9b405b843` on `feat/017-rust-native-inference-runtime`; exact-head full-native CI run `32601851854` succeeded.

Do not modify repository files. Do not open, hash, mmap, pread, or inspect original checkpoint payload bytes. Do not mint a live oracle or P1 authorization. Do not execute the target corrected oracle, retry P1 attempt 1, or execute P1 attempt 2. Synthetic and metadata-only adversarial tests are allowed. Repository bytes and direct CI evidence outrank this request.

## Acceptance question

Is the committed domain defensibly ready for a separate human decision to authorize exactly one corrected full-checkpoint scientific oracle event, while P1 attempt 2 remains blocked?

Recompute every binding in `specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v1.json` (SHA-256 `9ee8c20e7d78fbb008be777e4bf8affd1c9df780289048e1b149f5530e8b175f`). Also bind the numerical contract `ff0727f3…`, forward evidence v4 `41c46f55…`, geometry `a9037a42…`, synthetic qualification `fa366e11…`, and attempt-2 template `07fc9d55…`. Inspect CI run `32601851854` directly.

## Required attacks

### Forward evidence and lifecycle

- exact no-replace write, file fsync, directory fsync, descriptor-relative O_NOFOLLOW reopen, byte readback, strict schema, recomputed SHA, next-artifact binding for all load-bearing artifacts;
- real short/partial/write/fsync/dir-fsync/collision/readback/install/ENOSPC/receipt/terminal fault injections;
- all access attempt/result producers, tensor first/repeated use, unexpected/fallback/alternate-root/teardown/terminal summaries;
- RN1 exclusive owned claim: an invocation may terminalize only its own durable attempt; receipt counts outrank terminal claims;
- legacy current execution branch unreachable; attempt 1 remains immutable and explicitly nonconforming;
- path traversal, absolute/Unicode/NUL/overlength IDs, symlink ancestry, replacement, sibling ambiguity, pre-created attempt wedge.

### Independence and numerical methodology

- primary imports no production graph, Rust, FFI, MLX, production decoder/matvec, or prior diagnostic decoder;
- secondary shares neither primary graph, primary decoder, route logic, nor result writer; independently judge the explicitly bound pre-existing diagnostic decoder dependency rather than inheriting either Gemini cycle-01 or builder labels;
- 79-layer graph and all 11 formats are instantiable from catalog metadata; executable geometry binding mechanically agrees with Rust metadata authority;
- attention includes K reconstruction, Q/K RoPE, score, one-key softmax, V, output and residual; verify context/KV/mask semantics;
- target observations `21615`/`17351` cannot influence seeds, top-N, thresholds, safety factors, or success;
- numerical thresholds were frozen on non-target synthetic data. Attack the 65536 complexity safety-factor derivation and any underclaim of full-model uncertainty. A loose honest bound may lead to top-k/unstable/no-authority rather than exact-token acceptance; do not demand an exact token;
- route membership/order/ties precede numeric grading; full logits/top-32/margin/stability vocabulary is exact;
- 44 packed decoder cases and 16 named mutations genuinely exercise their stated surfaces and localize defects.

### Scientific access and attempt 2

- separate primary and secondary consumer authority/accounting; no ambient grant inheritance or event-directory collision;
- exact branch, implementation, producer, transitive decoder, geometry, catalog, manifest, six-shard, context, machine/memory, state/output roots;
- checkpoint identity read happens only after durable owned start, is fully receipted, and remains distinct from historical ledger units; preaccess performs zero payload reads;
- no fallback/alternate root/writable map; streaming is memory-bounded and has truthful progress/terminal semantics;
- authorization cannot be accidentally minted by validation and contains no expected token; live authorization count is zero;
- attempt-2 template inherits neither historical token, cannot instantiate before a separately executed and accepted oracle result, attempts=1/retries=0/resume=false/mandatory stop.

Re-run high-value mutations without original payload access. Reassess every Gemini cycle-01 finding and any defense-in-depth disposition. Use severities `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH`; both first two prevent acceptance. For every finding provide stable ID, exact path/symbol/evidence, failure mode, smallest repair, and CI/review impact.

Return exactly one final verdict: `ACCEPT` or `REJECT`.
