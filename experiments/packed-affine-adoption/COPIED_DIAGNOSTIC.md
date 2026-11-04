# Copied-control repair and prospective diagnostic

This branch repairs the private experimental bridge. It does not qualify a native
candidate. Copying remains the shipping default. The original failed candidate is
`190c64213135a756f5e3d61059036b9af2d78d7a`, tree
`1bd6cf2f01d5a921fd9c402a109f36072721274f`. Its evidence is immutable. The historical
ordinary QMM count remains unknown, and balanced retirement was not established.

## Bridge contract

`native/adoption_bridge.mm` contains only the platform queries. Both that wrapper
and the host ABI test include `native/adoption_bridge_core.h` directly. Producers
receive empty destinations. The bridge accounts every nonempty returned handle
once, including partial results on status, callback or exception failures, before
validating the operation. It refuses empty success, nonempty destination reuse,
duplicate accounting and an overflowing bounded handle registry. Temporary flat
views and raw metadata are released only after their producers succeed. Adopted
parents survive their views. A failure poisons the context; subsequent operations
and cleanup are refused. Process exit remains the quarantine boundary.

Diagnostic mode writes bounded function/substage entry/return records to a
create-only `bridge-events.jsonl`. The handler retains at most 255 original error
bytes, with explicit truncation and first-writer state, without allocation, native
calls, pool access, locks or exceptions. Actual MLX integer return status is
separate from bridge refusal and from APIs that return a handle, pointer or shape.
The read-only failure snapshot never calls MLX or attempts cleanup. It distinguishes
QMM graph construction, evaluation attempts/completions, synchronization and
retirement. Graph construction alone does not prove GPU kernel completion.

The Rust child writes and syncs each verified source-read receipt **before** native
preparation. Detailed diagnostics are enabled only for diagnostic modes. The full
M1a parent, qualifier, performance policy, range reader, references, native pins
and patches are unchanged. Do not use the full M1a parent for this diagnostic.

## Host-only regression commands

Use an existing pinned MLX C header tree; do not install a runtime or dependencies.
The fake ABI returns empty `mlx_array_new` results and populates producer outputs.
It is linked only to the production core and ordinary host C++ libraries. The
runner checks linkage before executing one serial test process at a time. Its
immutable old-source control returns 42 because the same success expectation
fails before either metadata cast. Fake numerical values are never acceptance.

```sh
python3 -B experiments/packed-affine-adoption/tools/test_bridge_host.py \
  --headers "$PINNED_HEADERS" --out "$NEW_HOST_TEST_OUTPUT"
python3 -B -m unittest discover \
  -s experiments/packed-affine-adoption/tools -p test_copied_diagnostic.py -v
CARGO_BUILD_JOBS=2 RUST_TEST_THREADS=1 CARGO_NET_OFFLINE=true \
  CARGO_TARGET_DIR="$HOST_TARGET" cargo test --offline --locked \
  --manifest-path experiments/packed-affine-adoption/Cargo.toml \
  --no-default-features --test copied_diagnostic -- --test-threads=1
```

Inspect imports, build scripts, feature selection and linkage before any local
execution. No native-linked discovery, broad test suite or consolidated historical
command belongs on the host-only MacBook. Keep native prefix/require variables
unset for host builds. Use a fresh output directory to preserve failed attempts.

## Future operator-launched Studio diagnostic — not executed by this repair

The separate operator prompt must bind the returned exact new source commit/tree.
A branch name is only a discovery aid. Identify the current repository/common Git
directory and all relevant worktrees first. Preserve any GLM checkout, staged,
unstaged and untracked work, and other owners. Reuse a clean exclusively owned
experiment worktree at the exact admitted commit/tree, or create a fresh detached
one when that separate prompt authorizes setup. Do not switch, stash, reset, clean,
rebase or overwrite the GLM worktree. A dirty GLM checkout is not a global blocker.
Keep all targets and receipts outside source; recheck selected HEAD/tree/status
before freeze and again before native execution.

The following are **prospective templates**, not authorization or commands executed
on either machine by this repair. Substitute the exact returned commit/tree and
explicitly selected paths from the separately issued work order. Do not use a
moving branch tip. Existing pinned native installation and locked Cargo inputs
must already be available; no reinstall, dependency fetch or toolchain change is
part of these commands. Record fresh compiler/linker captures and inspect produced
executable paths from Cargo JSON.

```sh
cd "$SOURCE_WORKTREE"
git rev-parse --show-toplevel HEAD 'HEAD^{tree}'
git status --porcelain=v1 --untracked-files=all
CARGO_BUILD_JOBS=2 RUST_TEST_THREADS=1 CARGO_TARGET_DIR="$NATIVE_TARGET" \
  MLX_PREFIX="$PINNED_PREFIX" MLX_C_PREFIX="$PINNED_PREFIX" \
  cargo build --offline --locked --release \
  --manifest-path experiments/packed-affine-adoption/Cargo.toml \
  --features native-adoption --bin adoption-probe --message-format=json

env -u MLX_PREFIX -u MLX_C_PREFIX -u PULSAR_REQUIRE_NATIVE_MLX \
  CARGO_BUILD_JOBS=2 RUST_TEST_THREADS=1 CARGO_TARGET_DIR="$HOST_TARGET" \
  cargo build --offline --locked --release \
  --manifest-path experiments/packed-affine-adoption/Cargo.toml \
  --no-default-features --bin grade-rust --message-format=json

python3 -B experiments/packed-affine-adoption/tools/copied_diagnostic.py freeze \
  --source-commit "$EXACT_DIAGNOSTIC_COMMIT" --source-tree "$EXACT_DIAGNOSTIC_TREE" \
  --freeze "$OLD_CAMPAIGN/freeze.json" \
  --failure "$OLD_CAMPAIGN/m1a/group-0-copied/run.json" \
  --raw-intent "$OLD_CAMPAIGN/raw-probe.intent.json" \
  --raw-report "$OLD_CAMPAIGN/m1a/raw-probe/run.json" \
  --fixture-root "$ORIGINAL_INPUTS/fixtures" --portable "$ORIGINAL_INPUTS/portable.json" \
  --reference "$ORIGINAL_INPUTS/reference.json" --native-prefix "$PINNED_PREFIX" \
  --native-build-receipt "$ORIGINAL_NATIVE_BUILD_RECEIPT" \
  --binary "$NATIVE_TARGET/release/adoption-probe" \
  --rust-grader "$HOST_TARGET/release/grade-rust" --output "$NEW_DIAGNOSTIC_ROOT"

PULSAR_COPIED_DIAGNOSTIC=studio-copied-only-v1 \
  python3 -B experiments/packed-affine-adoption/tools/copied_diagnostic.py run \
  "$NEW_DIAGNOSTIC_ROOT/diagnostic-receipt.json"
python3 -B experiments/packed-affine-adoption/tools/copied_diagnostic.py check \
  "$NEW_DIAGNOSTIC_ROOT/diagnostic-receipt.json"
```

`PULSAR_ADOPTION_PHASE` must be absent. Freeze/run refuse a non-Studio host, CI,
changed source, missing/crossed original receipts, changed original inputs or
native installation, and a different parent/interpreter/binary/grader. The parent
rehashes sources and receipts before its only launch. The child rechecks its
copied-only receipt and original byte identities before native preparation.

The admitted child is `copied-diagnostic-v1`, copied arm, one child, 300 seconds,
no warmups or timing sweep, and exactly this A–B–A sequence:

1. `mlp-d128-h64-m1-e0-default-gate`
2. `mlp-d128-h64-m1-e1-default-gate`
3. `mlp-d128-h64-m1-e0-default-gate`

It retains the original fixtures, three buffered reads per fill, payload hashes,
full-slab diagnostics, 32 MiB working/native requested limits, 96 MiB combined
logical reservation, five-second retirement acknowledgement and process-exit
quarantine. These are not an OS physical-memory cap. Original input geometry is
M=1, N=64, K=128, four-bit affine, group size 64, BF16 metadata and F32 output.

## Receipt and failure semantics

The separate schema is `pulsarmlx.copied-diagnostic-receipt/1`. It binds:

- Original freeze, copied failure, raw intent and raw report by their exact byte
  hashes in `copied_diagnostic::ORIGINALS` / `copied_diagnostic.py::ORIGINALS`.
  Sanitized publication values cannot replace original local files.
- Raw used=1, allowed=1, execution_authorized=false. No full-M1a freeze is created.
- Exact new source commit/tree, all original 53 source paths plus the current
  experiment paths, compiled child, parent script, Python interpreter, Rust grader,
  native build receipt/libraries and original fixture/reference identities.
- Copied-only scope, three projections, one child, 300 seconds, no retry, no M1a
  acceptance and no performance claim.

`launch.intent.json` is create-only and written before any child launch. Unknown
results remain consumed. An occupied claim/output directory is never cleaned or
reused. The launch is under a cleared environment with TF32 off, the bound native
prefix, fixed timeout, kill/reap and no retry. Failures preserve stdout, stderr,
source-read events, bounded bridge trace, first-error bytes and read-only ownership
snapshot. Do not infer balanced retirement from process exit or fill unknown fields
by attempting native cleanup.

The separately labelled `diagnostic-check.json` verifies the exact three saved
outputs through the unchanged Rust and original-byte exact reference gates. It
also verifies call entry/return order, graph/eval/sync counts, source-read receipts
and balanced copied-path retirement. It never calls the whole-population qualifier
or writes `mechanism.json` / `m1a-acceptance.json`. A diagnostic pass is not M1a
acceptance, a raw-probe allowance, cross-candidate reuse permission or a timing
release. Preserve original errors privately; publish separately sanitized copies
with distinct original/publication hashes.

## Stable diagnostic IDs

The next tables are the enum ordinals from the production core. Phase 1 is entry,
2 is return, 3 is refusal. `mlx_status_known=false` means no MLX integer return
status was observed. First-error capture state 0 is absent, 1 is in-flight/unknown,
2 is complete. Category 1 is an MLX callback, 2 a standard C++ exception and 3 a
non-standard C++ exception. In-flight text is not read. No latch is reset.

| Function ID | Meaning |
| --- | --- |
| 0 | `None` |
| 1 | `Open` |
| 2 | `Register` |
| 3 | `DropSlot` |
| 4 | `Input` |
| 5 | `Prepare` |
| 6 | `Project` |
| 7 | `CopyControl` |
| 8 | `Memory` |
| 9 | `ResetPeak` |
| 10 | `Retire` |
| 11 | `Close` |
| 12 | `Sync` |

| Stage ID | Meaning |
| --- | --- |
| 0 | `Begin` |
| 1 | `Device` |
| 2 | `Stream` |
| 3 | `StreamIndex` |
| 4 | `MemoryLimit` |
| 5 | `CacheLimit` |
| 6 | `ClearCache` |
| 7 | `ResetPeakStage` |
| 8 | `Synchronize` |
| 9 | `ImportParent` |
| 10 | `ParentIdentity` |
| 11 | `ImportWeight` |
| 12 | `Slice` |
| 13 | `Reshape` |
| 14 | `ViewEval` |
| 15 | `ViewIdentity` |
| 16 | `ImportScales` |
| 17 | `ImportBiases` |
| 18 | `CastScales` |
| 19 | `CastBiases` |
| 20 | `FreeRawScales` |
| 21 | `FreeRawBiases` |
| 22 | `ImportInput` |
| 23 | `Shape` |
| 24 | `Qmm` |
| 25 | `Evaluate` |
| 26 | `CopyOutput` |
| 27 | `FreeOutput` |
| 28 | `FreeFlat` |
| 29 | `FreeWeight` |
| 30 | `FreeScales` |
| 31 | `FreeBiases` |
| 32 | `FreeInput` |
| 33 | `FreeParent` |
| 34 | `FreeStream` |
| 35 | `FreeDevice` |
| 36 | `ActiveMemory` |
| 37 | `CacheMemory` |
| 38 | `PeakMemory` |
| 39 | `CopyImport` |
| 40 | `CopyIdentity` |
| 41 | `CopyFree` |
| 42 | `End` |

| Refusal ID | Meaning |
| --- | --- |
| 0 | `NoRefusal` |
| 1 | `InvalidInput` |
| 2 | `PriorFailure` |
| 3 | `NonemptyDestination` |
| 4 | `DuplicateHandle` |
| 5 | `AccountingFull` |
| 6 | `EmptyResult` |
| 7 | `NativeStatus` |
| 8 | `ErrorCallback` |
| 9 | `Exception` |
| 10 | `UnknownHandle` |
| 11 | `EvidenceWrite` |
| 12 | `InvalidResult` |
