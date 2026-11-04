# Packed-affine adoption: bounded M0/M1 experiment

Shipping remains `copied`. This package is an isolated workspace; its default
build and tests contain no MLX linkage. Only `adoption-probe`, behind the explicit
`native-adoption` feature, links the private bridge. Nothing here attaches to the
engine or changes frozen qualification modes, gates, native pins or install
patches. M2–M4 are outside this experiment.

## Source and fixture freeze

`dependency-manifest.json` records the original snapshots and exact imported
files. The read-plan implementation comes from the pinned ranges snapshot; the
new `read_into` module adds a checked, role-scoped destination and consumes a
`FilledPlane` before native access. The `selected_preflight` function is extracted
unchanged from the pinned selected adapter; imports are adapted to this package.
The baseline coordinator and routed-composition source are unchanged.

The tracked `fixtures/expert-mlp-composition/checkpoints/d128-h64-*` files are tiny
synthetic fixtures from the approved snapshot. They are not model checkpoints.
`generate_envelopes.py` preserves their config/shard bytes, adds explicit indexes,
and uses the original closed-form full-size generator to produce A/B input and
component bytes. It creates new indexed Safetensors envelopes; old PLSEX metadata
is never passed off as new source identity. It refuses an occupied output path.

Portable sequence, with `STATE` set to a new private artifact directory:

```sh
export CARGO_BUILD_JOBS=2 RUST_TEST_THREADS=1
export CARGO_TARGET_DIR="$STATE/target-host"
cargo test --offline --locked -p mlx-expert-ranges --lib --test ranges --test read_into -- --test-threads=1
cargo test --offline --locked --manifest-path experiments/packed-affine-adoption/Cargo.toml --lib --test portable -- --test-threads=1
cargo build --offline --locked --manifest-path experiments/packed-affine-adoption/Cargo.toml --bins
python3 -B experiments/packed-affine-adoption/tools/generate_envelopes.py --out "$STATE/fixtures"
# Read the manifest digest from the generator's result; do not substitute one.
"$CARGO_TARGET_DIR/debug/portable-check" "$STATE/fixtures" "$FIXTURE_SHA256" "$STATE/portable.json"
python3 -B experiments/packed-affine-adoption/tools/reference.py --root "$STATE/fixtures" --manifest-sha256 "$FIXTURE_SHA256" --portable "$STATE/portable.json" --out "$STATE/reference.json"
python3 -B -m unittest discover -s experiments/packed-affine-adoption/tools -p test_report_checks.py -v
```

Repeat the two Rust test selections with `--release` for release coverage. Do not
run the repository's consolidated historical/native suite on the MacBook. The
explicit portable selections above were inspected for imports and child launches.
They are not a general execution sandbox. Inspect any changed selection first.
Do not enable `native-adoption`, run native-linked artifacts, import MLX, access
real model/tokenizer files, or install dependencies on the MacBook.

## Native host handoff (pending, not a MacBook command)

M1a is required independently on the approved native CI route and physical
Apple M1 Ultra Studio. M1b belongs only to Studio after both M1a acceptances. A
local source commit is not source-publication or CI-dispatch permission. Use the
existing owner on each route; do not start another owner or spend an unknown
raw-probe attempt. No workflow or gate changes are included here.

1. Transfer the exact local source commits in the review handoff and immutable fixture,
   portable and reference artifacts through an approved route. Verify the source
   commit/tree from the result handoff. Preserve the existing 32-case Slice 2C
   fixtures, original qualifier and accepted evidence. The new population is
   separate: 14 inherited positives per arm, 8 small A-B-A groups per arm (24
   dispatches), and 4 representative projections per arm.
2. On the named native host, inspect the installed MLX/MLX C build provenance:
   `68cf2fddd8de5edd8ab3d926391772b2e2cedad8` and
   `0726ca922fc902c4c61ef9c27d94132be418e945`, including all four unchanged patches
   in `scripts/ci/install_native_mlx.sh`. Preserve the build receipt/log. A library
   hash alone does not establish its source. Do not install to evade missing
   prerequisites. Set `MLX_PREFIX` and `MLX_C_PREFIX` to that same existing prefix.
3. Build, without running, with two jobs and the explicit feature:

   ```sh
   CARGO_BUILD_JOBS=2 cargo test --offline --locked --release --manifest-path experiments/packed-affine-adoption/Cargo.toml --features native-adoption --test adoption_parent --no-run --message-format=json > "$STATE/native-build.jsonl" 2> "$STATE/native-build.stderr"
   ```

   Capture the exact `adoption-probe` executable and test-parent paths from Cargo
   output. Do not guess the parent hash-suffixed filename. Inspect `otool -L` for
   both; only the child may link MLX. Also build the default portable `grade-rust`
   binary and inspect its linkage. Use a fresh campaign directory; retain all
   build failures. Native compilation/linking is pending until this succeeds.
4. Freeze actual source, binary, parent, grader, installed-library/metallib,
   host and fixture identities before any candidate observation:

   ```sh
   python3 -B experiments/packed-affine-adoption/tools/freeze_host.py \
     --host-role "$ROLE" --source-commit "$SOURCE_COMMIT" \
     --campaign "$CAMPAIGN" --fixture-root "$STATE/fixtures" \
     --portable "$STATE/portable.json" --reference "$STATE/reference.json" \
     --native-prefix "$MLX_C_PREFIX" --native-build-receipt "$NATIVE_BUILD_RECEIPT" \
     --binary "$ADOPTION_CHILD" --parent "$ADOPTION_PARENT" --rust-grader "$RUST_GRADER"
   ```

   `ROLE` is exactly `native-ci` or `m1-ultra-studio`. Complete CI first, then add
   `--native-ci-acceptance "$CI_ACCEPTANCE"` when freezing the Studio campaign.
   The helper verifies bytes and host, but the host owner must reconcile the
   pinned installation's source/patch receipt and candidate build capture. Keep
   these captures private; sanitize local paths only in the publication copy.
5. Run the already-built MLX-free parent once (one test thread):

   ```sh
   PULSAR_ADOPTION_HOST_ROLE="$ROLE" PULSAR_ADOPTION_CAMPAIGN="$CAMPAIGN" \
     "$ADOPTION_PARENT" --exact required_native_m1a --test-threads=1 --nocapture
   ```

   The parent records intent before the raw constructor call. The isolated raw
   `P/4-1` probe has a 60 s watchdog and no QMM. A timeout qualifies only after
   SIGKILL/reaping; an unknown attempt stays spent. Ordinary diagnostic children
   have 300 s each. Failed adoption or uncertain ownership stops that child with
   quarantine; it cannot allocate a replacement and continue measuring. Keep the
   entire campaign on failure, including config/outcome/stdout/stderr/events.
6. Complete independent original-byte mathematical gates using the MLX-free
   grader and unchanged exact reference functions (900 s per reference child):

   ```sh
   python3 -B experiments/packed-affine-adoption/tools/qualify_reports.py \
     "$CAMPAIGN" --rust-grader "$RUST_GRADER"
   ```

   `mechanism.json` is not numerical acceptance. The adapter requires the exact
   52-report set, source/binary/native/config/fixture bindings, actual saved
   outputs, copied/adopted identity, original gates and balanced retirement. It
   creates `m1a-acceptance.json` only after all gates pass. Each invocation is
   create-only: reconcile an existing attempt rather than deleting it to retry.
7. On Studio only, after both accepted receipts match source/tree and fixtures,
   invoke the same parent with `PULSAR_ADOPTION_PHASE=m1b`. It rechecks the Studio
   executable/native identities and saved accepted reports. Four warmups precede
   every timing block. Baseline-only A/A calibration precedes candidate timing;
   fill counts 128/512, resident counts 4096/16384, one retry per unsuitable mode,
   fixed 5% practical benefit and frozen noise policy, at most one reversed
   follow-up. Held-out B-up and the resident companion are released only in the
   prescribed order. Child watchdog 120 s; total timing budget 30 min. Preserve
   every block and terminal `decision.json`. Do not increase budgets or run M2.

No M1 result is inferred from compilation. If native execution is unavailable,
report M1a pending and M1b held. A neutral/failed/inconclusive result is valid and
keeps the copied default. No expert paging or production residency is claimed.

## Ownership and accounting

Two initialized page-aligned slots share one flat U32 parent. Only private,
short weight-range borrows exist during quiescent fills. Views, copied metadata,
inputs and outputs stay inside the single native context/stream. Diagnostic
hashes cover the complete padded allocation; timing omits those diagnostic
hashes but retains three exact reads, operational SHA verification and identical
metadata copying/widening in both arms. Resident blocks retain both slot inputs
and views and do not refill them.

The callback retains its token independently and performs one release-ordered
atomic acknowledgement without MLX/pool calls. The owner retires graphs and the
parent, waits at most five seconds, verifies category/total handle balances and
only then deallocates. Failed/uncertain retirement leaks the quarantined slab to
child process exit; it does not guess that native ownership ended.

Live working data is bounded at 32 MiB; requested MLX memory/cache limits are
32 MiB each; the logical combined reservation is 96 MiB including separately
bounded host instrumentation. Raw native counters and adopted capacity are
reported separately. They are not proof of process RSS, physical wiring, exact
allocator overlap or zero hidden materialization. Physical device I/O is unknown.

## Copied-control source continuation

The [copied diagnostic documentation](COPIED_DIAGNOSTIC.md) describes the output-handle
repair, host-only regression and separate prospective copied-only route. It grants
no native execution, raw-probe retry, full-M1a acceptance or timing release.
