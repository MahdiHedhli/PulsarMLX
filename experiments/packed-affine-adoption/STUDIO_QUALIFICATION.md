# Original-byte Studio qualification bridge

This is a host-tool implementation, not a Studio execution grant. Copying stays
the shipping default; M1b and M2–M4 remain held. The bridge never launches a
native child. Its only numerical child is a separately identified MLX-free
`grade-rust` built from C. Each stage is a separate Python process.

| Role | Commit | Tree |
| --- | --- | --- |
| Native C | `f61a8c19d6aad2265a12f417ddbe842024fe32f2` | `5f8a8c55f4e0067b10dcd6606fe05935e8e47659` |
| Rational Q | `14ac1c7e1ffaf8c25b160bcca7cdbe9abf57cd41` | `b611e3dd7f40947b8409ca574d5f6ccdcd67ee02` |
| Controller H, preserved | `8a21f17bdea7b9d04f7ac54b070fa0a4f12762a2` | `f08812602debc2fce192e2035339844c6c284ef0` |
| Orchestration R | Exact commit/tree returned by Rust012 | Supplied by the later work order |

The later authority pins R after its source commit exists. No self-referential
commit is embedded in these files. All 5,085 C files and five Q additions,
including modes and types, must match their original Git blobs.

## Interface and seals

`tools/studio_qualify.py` has three stages:

* `prepare` verifies sources/imports, the later authority, original custody,
  physical host/native state, binaries/linkage, inputs and the completed CI
  prerequisite. It writes only `<OUTER_STATE>/ready.json` and returns its hash.
* `bind --ready-sha256 HASH` admits the unchanged C freeze and its native claim,
  before any native parent attempt. It writes `<OUTER_STATE>/bound.json` and
  returns its hash.
* `qualify --bound-sha256 HASH --parent-completion PATH` requires observed parent
  exit 0, complete live C admission and original reports. It exclusively claims
  one numerical pass, grades the complete population and re-admits all inputs,
  source and evidence before returning a distinct result.

Every command also requires `--authority PATH --authority-sha256 HASH
--c-source PATH --q-source PATH`. R derives its own actual root. C's validators
are loaded from C, Q's rational module from Q. Exact origins include
`f020_selected_r1_v2` and its `f020_expert_mlp_r1_v1` dependency; all thirteen
helper hashes are pinned in `studio_bridge.PINS`. Preloaded/shadow modules
refuse admission. Bytecode writes are disabled.

The original installation receipt must remain at the location recorded in the
immutable Studio001 freeze and Studio002 diagnostic receipt. Its parent owns
`f020-m1a-continuation.claim.json` (C's native claim) and
`f020-studio-m1a-numerical.claim.json` (R's numerical claim). A copied receipt,
new output root, new worktree or new R revision cannot refund either claim.
An unknown, failed or interrupted numerical claim is spent. R has no resume.

The new result is `<RESULT_ROOT>/studio-live-m1a-acceptance.json`, schema
`pulsarmlx.studio-live-m1a-acceptance/1`. It never aliases legacy acceptance.
On failure it records `FAILED_NO_RETRY`, partial rows and failure details. If
the output directory could not be exclusively created, failure is written to
the already owned outer state instead of the foreign directory.

## Fields the later operator authority must seal

The later work order supplies an exact SHA-256 for an original local JSON file
and its adjacent `<hash>  <filename>` sidecar. Its schema is
`pulsarmlx.studio-m1a-operator-authority/1`. Rust012's implementation prompt and
synthetic authority are rejected. This file is an operator grant; do not infer
one from repository publication or generate it as part of Rust012.

| Field | Required value |
| --- | --- |
| `purpose`, `evidence_role` | `STUDIO_FULL_M1A_ONCE`, `OPERATOR_AUTHORITY` |
| `launch_authorized`, `synthetic` | `true`, `false` |
| `phase`, `host_role`, `raw_policy` | `m1a`, `m1-ultra-studio`, `STUDIO_RETAINED_OBSERVATION` |
| `contract_sha256` | `7d28d6a427606dd622d3e00d362757365b51990972be8a4e7ee17131d5297d2d` |
| `contract_path` | Original verified 15,561-byte bridge contract |
| `prompt` | Actual later Studio prompt `commit`, `sha256`, original local `path`; adjacent checksum required |
| `sources` | Exact `{commit,tree}` for C, Q and returned R |
| `roots` | Separate clean canonical absolute C/Q/R checkout locations |
| `native_parent_allowance`, `numerical_allowance`, `new_raw_allowance` | `1`, `1`, `0` |
| `M1b_released`, `shipping_default` | `false`, `copied` |
| `paths` | Exactly `state`, `campaign`, `output`, `fixture_root`, `portable`, `reference`, `native_prefix`, `native_install`, `binary`, `parent`, `grader`, `originals` |
| `original_custody` | Every key in C's `continuation-studio-originals-v1.json`, mapped to its actual original Studio location; equals the JSON at `paths.originals` |
| `executables` | `binary`, `parent`, `grader`, `python`, each with actual canonical `path` and actual per-host `sha256` |
| `build_identity` | Original local receipt `path` and its `sha256` |
| `ci_files` | Original local `response`, `response_checksum`, `handoff`, compressed `supplement`; optional `original_supplement` has its separately declared original identity |

Build identity schema is `pulsarmlx.studio-c-build-identity/1`, with C
`source_commit`/`source_tree`, the same four `executables`, and `linkage` keyed
by those roles (exact `otool -L` lines after the filename header). Retain build
argv, successful Cargo JSON artifacts, compiler/linker captures and hashes as
additional evidence. Select exactly the built child/parent/grader; do not glob
for an arbitrary executable. Existing binaries may be reused only with verified
C source/build provenance. No dependency or native reinstall fallback exists.

`ci_files` comes from private publication
`bc38ce3d7d5aa140f82b8da097689ffa232fae0f`. The compressed supplement is
799,510 bytes, SHA-256
`ccf08f1e7c18e34566c3b80d7347d1c1f99497b48c36038234c61dfb89eb8c1f`.
Bounded decompression admits exactly 6,425,177 bytes with SHA-256
`c79d6a12493adcffc72df0b450b2a0140c10425854e44f4bd720230e39c21273`.
It is distinct from the 6,425,327-byte local original with SHA-256
`1507dac4e9a861ff32d0b5c1c0c0b41bea4ed58e8afc432a4b5540f9a5b80d3c`.
The verifier inspects all saved gate decisions and bindings without regrading
old outputs. CI prerequisite kind is `RETAINED_C_MECHANISM_PLUS_Q_NUMERICS`;
run 41933197121/1 remains failed. Its 124 publication control views and missing
original controls/native executable bytes retain their declared limitations.

## Prospective Studio sequence — not authorized here

First inventory every Studio worktree/HEAD/tree/status and preserve dirty GLM
entries. Create separately owned clean C/Q/R worktrees at the exact returned
pins, using normal `git worktree add --detach` in a verified repository. Do not
switch or clean GLM. Verify physical Mac13,2, Apple M1 Ultra, 128 GiB,
16,384-byte pages, macOS 26.0/build 25A354 and the retained native installation.
Verify every original Studio001/002 file, its custody location and both stable
claim paths before work. Unknown host/provenance or occupied claims stop.

The following shell variables are typed local roles resolved and checked by
that later owner, not guessed paths: `C_SOURCE`, `Q_SOURCE`, `R_SOURCE`,
`NATIVE_PREFIX`, `NATIVE_INSTALL_ORIGINAL`, `ORIGINALS_MAP`, `FIXTURE_ROOT`,
`PORTABLE`, `REFERENCE`, `CAMPAIGN`, `OUTER_STATE`, `RESULT_ROOT`,
`NATIVE_TARGET`, `GRADER_TARGET`, `C_CHILD`, `C_PARENT`, `C_GRADER`,
`HOST_PYTHON`, `AUTHORITY`, `AUTHORITY_SHA256`, `READY_SHA256`, `BOUND_SHA256`,
`PARENT_COMPLETION`. The private result handoff supplies the actual R pin.

Reverify or build only required C binaries with existing offline locked inputs:

```sh
env CARGO_BUILD_JOBS=2 RUST_TEST_THREADS=1 CARGO_TARGET_DIR="$NATIVE_TARGET" \
  MLX_PREFIX="$NATIVE_PREFIX" MLX_C_PREFIX="$NATIVE_PREFIX" \
  cargo test --offline --locked --release \
  --manifest-path "$C_SOURCE/experiments/packed-affine-adoption/Cargo.toml" \
  --features native-adoption --test adoption_parent --no-run --message-format=json
env -u MLX_PREFIX -u MLX_C_PREFIX -u PULSAR_REQUIRE_NATIVE_MLX \
  CARGO_BUILD_JOBS=2 RUST_TEST_THREADS=1 CARGO_TARGET_DIR="$GRADER_TARGET" \
  cargo build --offline --locked --release \
  --manifest-path "$C_SOURCE/experiments/packed-affine-adoption/Cargo.toml" \
  --no-default-features --bin grade-rust --message-format=json
```

Capture/verify the build identities and seal the later authority. Each R call
uses a clean environment: no native-prefix/require, loader, model, Git override,
`PYTHONPATH`, `PYTHONHOME` or GitHub variables; only `PULSAR_ADOPTION_PHASE=m1a`
is required for C's live admission. Keep two build jobs and one test thread.

```sh
env PULSAR_ADOPTION_PHASE=m1a "$HOST_PYTHON" -B \
  "$R_SOURCE/experiments/packed-affine-adoption/tools/studio_qualify.py" prepare \
  --authority "$AUTHORITY" --authority-sha256 "$AUTHORITY_SHA256" \
  --c-source "$C_SOURCE" --q-source "$Q_SOURCE"
env PULSAR_ADOPTION_PHASE=m1a "$HOST_PYTHON" -B \
  "$C_SOURCE/experiments/packed-affine-adoption/tools/m1a_continuation.py" freeze \
  --host-role m1-ultra-studio --source-commit f61a8c19d6aad2265a12f417ddbe842024fe32f2 \
  --phase m1a --raw-policy STUDIO_RETAINED_OBSERVATION --campaign "$CAMPAIGN" \
  --fixture-root "$FIXTURE_ROOT" --portable "$PORTABLE" --reference "$REFERENCE" \
  --native-prefix "$NATIVE_PREFIX" --native-build-receipt "$NATIVE_INSTALL_ORIGINAL" \
  --binary "$C_CHILD" --parent "$C_PARENT" --rust-grader "$C_GRADER" --originals "$ORIGINALS_MAP"
env PULSAR_ADOPTION_PHASE=m1a "$HOST_PYTHON" -B \
  "$R_SOURCE/experiments/packed-affine-adoption/tools/studio_qualify.py" bind \
  --authority "$AUTHORITY" --authority-sha256 "$AUTHORITY_SHA256" \
  --c-source "$C_SOURCE" --q-source "$Q_SOURCE" --ready-sha256 "$READY_SHA256"
env PULSAR_ADOPTION_PHASE=m1a PULSAR_ADOPTION_HOST_ROLE=m1-ultra-studio \
  PULSAR_ADOPTION_CAMPAIGN="$CAMPAIGN" MLX_PREFIX="$NATIVE_PREFIX" MLX_C_PREFIX="$NATIVE_PREFIX" \
  RUST_TEST_THREADS=1 "$C_PARENT" --exact required_native_m1a --test-threads=1 --nocapture
```

The later owner must track that one parent, preserve stdout/stderr and observe
its exit/reap. It records schema `pulsarmlx.studio-parent-completion/1`, exact
`argv` from the final command (executable and its four arguments), actual
`exit_code`, `reaped`, `started_unix`, `ended_unix`, `bound_sha256`, C freeze
`receipt_sha256`, `parent_sha256`, and `stdout`/`stderr` objects with actual
`path`/`sha256`. A missing/unknown outcome cannot release qualification. This
capture is an observation made by the tracked supervisor, not a fabricated
success marker. No parent launcher is supplied by R.

After successful parent completion and capture, clear the parent's native/host
environment again and run exactly once:

```sh
env PULSAR_ADOPTION_PHASE=m1a "$HOST_PYTHON" -B \
  "$R_SOURCE/experiments/packed-affine-adoption/tools/studio_qualify.py" qualify \
  --authority "$AUTHORITY" --authority-sha256 "$AUTHORITY_SHA256" \
  --c-source "$C_SOURCE" --q-source "$Q_SOURCE" --bound-sha256 "$BOUND_SHA256" \
  --parent-completion "$PARENT_COMPLETION"
```

Native C retains 300-second child timeouts, 32 MiB working/native requests,
96 MiB logical reservation and five-second owner release. R retains 900 seconds
for the complete numerical pass and 256 MiB observed reference working data,
with each child's timeout limited by remaining time. Only its owned CPU child
is killed/reaped on interruption. These are not combined physical-memory caps.
Q's `frozen_view` preserves exact reference identity/geometry/census and applies
only lossless integer-to-fraction text compatibility. No numerical rule changes.

Return 52 reports, 84 projections, 76 Rust and 76 self-checks, eight explicit
full-K deferrals, original current-file hashes, complete gate rows and final live
admission. Keep C-native, Q-rational and R-orchestration identities separate.
Retain old raw history (no new call), all failures and original/publication
distinctions. Physical execution and combined M1a completion remain separate
from Rust012's host implementation readiness; M1b still needs its own decision.
