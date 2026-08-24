# F017 Lifecycle V6 Semantic Design Review — Cycle 04

Full review written to `/Users/mhedhli/.claude/plans/f017-lifecycle-v6-sequential-brook.md`. Repository untouched (`git status --porcelain` empty before and after); no shard opened/hashed/mmapped/pread, no Event-04 authority minted, no oracle executed, no P1 attempt 2. Every load-bearing byte came from `git cat-file -p bb15fe2:<path>`; all execution was in `/tmp` scratch on synthetic checkpoints.

## Independent reconstruction

Written from the model text rather than by importing project code, my reimplementation reproduced all 11 semantic-projection anchors (including `complete_model`), all 9 authority-file SHAs and all 9 manifest pairs against true bytes, canonical-byte identity of all 10 authority documents, the four derived documents exactly, and the whole binding surface — **163 identities, 29 artifacts, 4727 cells, 3918 required, 0 mismatches**. Committed tooling agrees (validator PASS with 56 mutations rejected; stdlib-only checker PASS; 29/29 tests pass).

## Both cycle-03 defects reproduced, then closed

**NBR-1.** `validate_authority_bindings()` now runs inside `parse_authorization()`, so it fires on the candidate *and* installed boundaries in *both* consumers before install is reachable. Zeroing **each of the 13** authority SHAs is rejected individually; the cycle-03 exploit (`"0"*64` everywhere passing authorizer → dual validation → install → handshake) no longer reproduces. Missing files fail closed; production path substitution is rejected by the canonical census; both capability reports are byte-checked; forged install receipts fail; synthetic qualification uses real bound SHAs and a structurally isolated root (non-`checkpoint` name, non-`synthetic-` shards, or a non-sibling catalog are all rejected).

**NBR-2.** The hex rule moved out of the artifact writer's `payload` subtree into the serializer itself; all three implementations now emit byte-identical output. Nonfinite values fail everywhere, decimal-float artifact bytes are rejected as noncanonical, exactly one newline is enforced, readback SHAs cover complete artifacts, and no artifact embeds its own SHA. On a real end-to-end run, `full_logits`, margins and every comparison metric bank as lowercase `float.hex()`; the frozen hex thresholds are bit-exact against the comparator's decimal literals. The pure core's `result_sha256` is popped at the wrapper boundary, and complete logits/top-32/per-layer digests/metrics remain validated and usable with decoding only at numerical edges — so `output_manifest_sha256` and `{primary,secondary}_result_sha256` now chain cross-runtime-stable bytes into `package_terminal`.

## Attacks

All 16 coordinated model-mutation + full-regeneration attacks rejected. Forged authority-path substitution, wrong capability bytes, alternate serialization, float/hex confusion, fabricated receipt/terminal SHAs, and independent-checker bypass (9 hostile-input variants) all rejected. Historical ledger verified at **175** from Git object `96503db7…`; numerical v3 and both pure cores unchanged; `active_live_generation: "NONE"`; Event 04 unauthorized and unexecuted; no P1 attempt 2.

Nine `DEFENSE_IN_DEPTH` items are in the file. The most useful: `capability_path` is the one grant path with no canonical pin (I minted a document pointing it at `README.md` with a matching SHA and it passed — nothing escalates, since producer/target-source/numerical-core/decoder/interface are each pinned to hardcoded constants, but the record of *which* capability document was reviewed is unbound); `geometry_path` is decorative though its bytes are bound; and the `PRODUCTION` branch of `validate_authority_bindings` has no executed coverage because the measurement manifest is not yet in the tree.

**BLOCKING: 0 · NON_BLOCKING_REQUIRED: 0**

`ACCEPT_LIFECYCLE_V6_SEMANTIC_DESIGN_FOR_IMPLEMENTATION`
