# Staged weighted copied MLP

This experimental executor connects the fixed weighted route to the two-slot staged residency cache. All native operations, retirement, the weighted fold and the coordinator commit execute on the request owner's thread. One scoped reader may read the next admitted wave into separate raw byte banks. The reader returns those banks before the synchronous call can succeed. Serial and Overlap have identical resources. Copying remains the shipping default.

## Source and host proof

The source base is `5110ab450e51d3e45383bb48ec351f3bb9ef96eb`, tree `29c60a1ba7756d542652cfe05c9b254780379995`. Three insertions select a new child module and a default-off feature/binary with its own link arguments. The original weighted executor, route book, numerical gates, native Driver, guard, staging core, fixtures and workflow retain their original bytes.

| Boundary | Source | Observation |
| --- | --- | --- |
| Composition | `weighted/staged.rs` | Opens the real copied cache, checks the fixed book, uses the original input reader and bounded occurrence records, and calls the shared occurrence pipeline and weighted sum under the real coordinator. The first delivery can fail after commit. Replay returns the same allocation. |
| Lifetime | `resident_native.rs`, `weighted_native_guard.rs`, `staged_weighted_native_child.rs` | One owner retains all Driver state. Uncertain retirement, unwind or failed finish quarantines the cache. Foreground failure, reader effects and cleanup are recorded separately. |
| Capacity | `weighted/staged.rs`, `f020_staged_weighted_check.py` | The pipeline includes the two resident slots, two staging banks, 2 MiB control and a requested 2 MiB reader stack. The executor adds 1,114,112 weighted bytes, 1,048,576 transport bytes and 33,554,432 native bytes exactly once. |
| Population | `f020_staged_weighted_check.py` | Unchanged AdmitAll predicts tickets, resident generations, recency, reads and explicit stage copies before the physical run. Separate transport JSON retains the actual mode. Original occurrence rows go directly to the cached-slot predicate, then ordered downs to both weighted gates. |
| Live identity | `f020_staged_weighted_supervise.py`, `f020_staged_weighted_bootstrap.py`, `staged_weighted_native_pins.rs` | Binds source, release artifact, retained installation, actual defining helper origins, six input hashes, original M2/M3 receipts and a fresh private description. Four serial children each require a startup verifier. |
| Cleanup | `wait_child` in the staged supervisor | A child and its startup verifier share one supervisor-owned process group. The outer deadline covers blocked startup I/O. After termination the supervisor observes the group and child for at most five seconds. An unresolved process stops launches and grading with the claim retained. |

Five preallocated 128 KiB journal slots retain the per-position transport receipts. The 983,168-byte transport proof includes their vector headers and counter, a 256 KiB live JSON tree budget and 64 KiB bookkeeping. A fixed plan contains at most 12 ticket transitions, each with one 32-byte binding. The fixed-size output cursor writes directly into the retained slot. The child streams each saved row separately and writes its summary through a separate bounded 128 KiB cursor. Allocator and OS overhead, requested stack size and process memory are distinct from logical charges. The separate 2 MiB harness allowance covers the bounded description response, snapshots, guards and report. The child output cap is 2 MiB on disk.

At the tested checkout, the default and mixed standing charges were 41,086,633 and 41,119,913 bytes. The five coordinator peaks add 1,028, 1,544, 1,548, 1,552 and 1,556 bytes respectively. The copied semantic control has its original smaller budget. [Complete host observations, ledgers, module hashes and schedules](host-evidence.json)

| Position | Demand | New stage ticket (wave, bank generation, expert) | Cumulative reads / component copies |
| ---: | --- | --- | ---: |
| 0 | A | (0, 1, A) | 9 |
| 1 | A B | (0, 2, B) | 18 |
| 2 | A B C | (1, 3, C) | 27 |
| 3 | A B A | (0, 4, A) | 36 |
| 4 | A C B | (0, 5, C), (1, 6, B) | 54 |

Each successful fixed arm uses bank zero for these six fills, visits twelve occurrences, observes six hits and four evictions, and joins five readers. The zero-weight C still executes. The host data includes actual speculative discards from a failed wave, exact complete success tickets and residents, moved-path ledgers, and four-arm synthetic numerical controls. The 23 arithmetic observations, 48 native occurrences and physical resource observations require separate hardware qualification.

## Prospective Studio preparation

A separate planner preparation order must supply the exact reviewed source commit/tree, a clean checkout, the original retained prefix, original receipts and fresh canonical destinations. All hardware paths, runtime/build facts, Cargo artifact and binary hashes, private description length/digest, launch envelope and timing remain unissued here. Preparation must reverify the physical Mac13,2 / Apple M1 Ultra / 128 GiB / 16 KiB pages, approved OS/toolchain, original MLX and MLX C revisions and the four retained installation patches. The original header evidence covers 29 included headers. No new C/C++ source or declaration was introduced.

These commands are for a later preparation order. Use the approved Rust 1.95.0 toolchain, fixed native prefixes and fresh external target and receipt paths supplied by that order. Start from the clean source root.

```sh
MLX_PREFIX="$APPROVED_PREFIX" MLX_C_PREFIX="$APPROVED_PREFIX" CARGO_TARGET_DIR="$FRESH_TARGET" \
  CARGO_BUILD_JOBS=2 cargo +1.95.0 build --release --offline --locked -p mlx-expert-mlp \
  --features staged-weighted-native --bin qualify-staged-weighted-mlp --message-format=json \
  > "$FRESH_CARGO_CAPTURE"
```

Preserve the exact original compiler-artifact line for the selected non-test release binary. Record its canonical path and SHA-256, the binary's path and SHA-256, commit, tree, prefix, unmodified ordered `otool -L` linkage lines, `verifier_modules`, `compiled_source_sha256`, `reference` and `accounting_abi_stamp` in the fresh build receipt. Compute the compiled source digest as SHA-256 of the original canonical JSON map from `compiled_sources()`. The actual binary must contain the matching embedded verifier/reference/source seal and the observed ABI witness. The binary and artifact receipt are separate originals.

Set `repo`, `prefix`, `binary`, `build`, `installation`, `freeze`, `diagnostic_receipt`, `output` and `private_description` in the fresh private preparation configuration. All are canonical absolute paths. Use the original custody locations and distinct fresh output and description destinations. Use a clean inspector environment with no native loader overrides for the following command.

```sh
/usr/bin/python3 -B scripts/research/f020_staged_weighted_supervise.py \
  describe-binding "$PREP_CONFIG" "$FRESH_PRIVATE_DESCRIPTION" > "$FRESH_ENVELOPE"
```

This prepares a fresh durable mode-0600 description. Its path-free envelope binds the exact original bytes. A separate planner launch decision must bind that envelope before any physical child runs. The original M2/M3 claims stay spent. The distinct staged claim is anchored beside the original installation receipt. No hardware execution, speedup, authentic replay or shipping change is established here.
