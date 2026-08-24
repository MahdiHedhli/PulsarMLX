# F017 lifecycle V8 causal design — Opus design review cycle 07

Use a fresh `claude-opus-5` high-effort session. This is the final authorized V8 design checkpoint. Review exact committed bytes at `781ce3ef` in a detached read-only worktree. Do not modify files or access original checkpoint shards.

Reconstruct cycle 06 and re-run its sole required finding. Descriptor `mode` is now proven to be an exact integer in `[0,2**32)` before `stat.S_ISREG`; negative and oversized modes must produce the standard `ValueError` rejection rather than `OverflowError`. The runtime suite contains both probes and now accounts for 216 rejected mutations. Re-attack all prior classification, lease-accounting, identifier-distinctness, descriptor, output-digest, prefix-immutability, and fixed-point restatement findings.

Adjacent closures also landed: lease IDs use the package identifier grammar, all five descriptors must identify regular files on one device with distinct inodes, and self/future reference counts are derived from the DAG rather than restated. Run the independent validator, 13 tests, all 48 symbolic outcomes, generator determinism, and coordinated forgeries.

Report `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH` separately. Required verdict exactly `ACCEPT_CHECKPOINT_IDENTITY_CAUSAL_DESIGN_V8_FOR_IMPLEMENTATION` or `REJECT`; any required finding must produce `REJECT`.
