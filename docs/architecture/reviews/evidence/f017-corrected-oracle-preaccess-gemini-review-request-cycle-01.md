# F017 Corrected Full-Checkpoint Oracle Preaccess Cross-Vendor Review — Cycle 1

You are the advisory cross-vendor reviewer. Review only committed bytes from a clean detached checkout of `feat/017-rust-native-inference-runtime` at implementation head `b9607b1e7bd2d9b58b849b9df9ecd5d810efcca8`. Repository evidence and direct CI evidence outrank this request. Do not modify files, open/hash/mmap/pread original checkpoint shards, mint a live authorization, execute the corrected target oracle, retry P1 attempt 1, or execute P1 attempt 2.

Reviewer identity must be `gemini-3.1-pro-high`, high effort, through AGY. Inspect exact-head CI run `32600160665` directly and recompute load-bearing file hashes.

## Authority and safety

Reconstruct the accepted attempt-1 offline closeout, immutable terminal failure, historical ledger SHA `aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e` and terminal 175. Verify that this phase performs zero original-checkpoint reads, zero oracle target executions, zero P1 attempt-2 executions, and creates no live authorization.

## Required attacks

1. Forward evidence: attack exclusive creation, file and directory fsync, descriptor-relative non-symlink readback, byte equality, strict schema reparse, readback-derived SHA, ordering, complete access producers, filesystem fault handling, receipt/terminal consistency, current legacy-path reachability, state-root/identifier traversal, and attempt-1 non-retroactivity. Determine whether the synthetic rehearsals test the actual producer rather than only helper methods.
2. Primary independence: inspect imports, file reads, subprocesses, decoders, graph, matvecs, routing, result writing, and target reader. Attack shared-code contamination and any reuse of production or prior diagnostic numerical implementation.
3. Secondary independence: determine whether it is actually separate from the primary and whether any reused diagnostic decoder or metadata helper makes the cross-check circular.
4. Full graph: verify all 79-layer-capable semantics are instantiable, including embedding, attention normalization, low-rank paths, K/V reconstruction, RoPE/KV/context/mask, dense/MoE, routing, eight experts, shared expert, residuals, final norm, output projection, full logits, top-32, and stable tie behavior. Attack missing K-RoPE, sequence/KV simplification, wrong orientation, route hardcoding, wrong format, and wrong final projection.
5. Quantization: inspect all 11 primary decoder implementations (F32, Q2_K, Q3_K, Q4_K, Q5_K, Q6_K, Q8_0, IQ2_S, IQ2_XXS, IQ3_XXS, IQ4_XS), especially corrected Q6_K and IQ3_XXS. Determine whether qualification actually exercises packed blocks and production-shaped tensor paths rather than merely declaring format coverage.
6. Numerical methodology: attack historical target-token leakage, post-hoc tolerance, empirical safety factor, target-derived top-N, weak top-1 stability, full-model uncertainty underclaim, route structural weakening, exact-token overclaim, and use of native output as an oracle. Verify that `21615` and `17351` are disclosures only.
7. Synthetic qualification: inspect seed predeclaration, fresh-process execution, primary/secondary agreement, full-logit metrics, route coverage, mutation localization, and whether mutations genuinely model the named defects. Attack fake mutation labels and unexercised quant formats.
8. Scientific access: attack alternate catalog/checkpoint/root/geometry, unbound producer, unverified shard identity, symlinks, writable access, access events emitted only after an action, missing attempt/result events, incomplete tensor-use census, ambiguous dual-consumer accounting, shared authorization inheritance, incomplete result comparison, unsafe failure handling, replay/resume, accidentally mintable authorization, and P1 authority leakage.
9. Attempt 2: prove the template cannot become executable without a future accepted corrected-oracle result and does not inherit either historical token.
10. CI routing: verify implementation paths select FULL_NATIVE and later evidence-only paths cannot launch native MLX; unknown paths must default full.

## Findings and verdict

Use `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH`. For each finding provide a stable ID, exact path/symbol, evidence, failure mode, and smallest repair. Distinguish a direct test result from inference. Material disagreement blocks progression until dispositioned.

Return exactly one top-level verdict:

- `GEMINI_ADVISORY_ACCEPT`
- `REJECT`

Also state original checkpoint reads during review, corrected target-oracle executions, P1 attempt-2 executions, and live authorizations; all must be zero.
