# F017 Corrected Full-Checkpoint Oracle Preaccess Final Review — Cycle 1

You are the final independent adversarial reviewer. Use a fresh `claude-opus-5` high-effort session. Review only committed bytes from a clean detached checkout of `feat/017-rust-native-inference-runtime` at implementation head `b9607b1e7bd2d9b58b849b9df9ecd5d810efcca8`. Repository evidence and direct CI evidence outrank this request. Do not modify files, open/hash/mmap/pread original checkpoint shards, mint a live authorization, execute the corrected target oracle, retry P1 attempt 1, or execute P1 attempt 2.

Inspect exact-head CI run `32600160665` directly and recompute all load-bearing hashes. Reconstruct the attempt-1 closeout and all accepted offline-review defense-in-depth findings rather than inheriting their prior severities.

## Required attacks

### Forward evidence

Attack exact serialized readback (exclusive create, fsync, parent fsync, descriptor-relative O_NOFOLLOW reopen, exact bytes, strict schema, readback SHA), physical filesystem faults, complete production access-event producers, ordering, state-root and identifier attacks, receipt/terminal/native-event binding, RN1 ownership, terminalization of only the owned attempt, current legacy-arm reachability, and attempt-1 non-retroactivity. Verify normal synthetic token mismatch retains durable pre/post snapshots, access census, diagnostics, failure receipt, terminal, one attempt, no retry, and mandatory stop.

### Oracle independence and quantization

Attack primary production imports, Rust/FFI/MLX reuse, production checkpoint reader reuse, shared prior diagnostic decoders, shared graph/route/result logic, hidden expected values, and circular fixture generation. Attack secondary independence from the primary. Audit all 11 formats and especially corrected Q6_K and IQ3_XXS. Determine whether tests exercise real packed bytes and production-shaped paths, and whether mutation localization genuinely injects each named defect.

### Numerical methodology

Attack post-hoc thresholds, unjustified empirical factor, target-derived top-N, historical token leakage, full-model error underclaim, weak top-1 stability, route structural weakening, exact-token overclaim, and native observation used as oracle. Verify full-logit/top-32 and exact outcome vocabulary. Confirm each future oracle outcome maps fail-closed into the P1-attempt-2 policy.

### Full graph and instantiability

Trace embedding, all 79-layer-capable attention and FFN paths, Q/K/V low-rank projections, K/V reconstruction, RoPE position and both Q/K semantics, attention/KV/context/mask behavior, dense/MoE transition, exact route ordering/ties, eight experts, shared expert, residuals, final norm, output projection, logits, top-N, and argmax. Attack wrong orientation, missing layer/tensor, route hardcoding, missing format, and incomplete memory-bounded target execution.

### Scientific access

Attack alternate contract/catalog/geometry/checkpoint roots, missing shard/tensor hashes, symlink and path replacement, access before durable claim, open attempts without receipts, incomplete first/repeated-use census, absent teardown/summary, ambiguous two-consumer accounting, one consumer inheriting another's grant, state replay, accidental live authorization, receipt/terminal mismatch, recovery ambiguity, and leakage into P1 authority. Confirm the target authorization contains no expected token and cannot be minted by ordinary validation.

### CI and attempt 2

Verify exact-head FULL_NATIVE CI directly, required test wiring, no required native skip, evidence-aware routing, and evidence-only zero-native behavior. Prove the attempt-2 template rejects execution without an accepted future oracle result and does not inherit `21615` or promote `17351`.

## Severity and verdict

Use `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH`. Both first two prevent acceptance. For every finding provide a stable ID, exact path/symbol, evidence, exploit/failure mode, smallest repair, test/CI impact, and whether prior numerical evidence is invalidated. Promote prior defense findings if they weaken the future live boundary.

Return exactly one top-level verdict:

- `ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EXECUTION_AUTHORIZATION_PREPARATION`
- `REJECT`

Acceptance does not mint or execute the oracle event and never authorizes P1 attempt 2. State original checkpoint reads, target-oracle executions, P1 attempt-2 executions, and live authorization count during review; all must be zero.
